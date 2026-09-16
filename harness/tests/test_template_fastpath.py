"""spec F3：运行时 fast path（锚点抽取→既有校验链→降级；管道集成与 data_quality）。"""

import json
import re
from pathlib import Path

from insurance_harness.compiler.llm import ReplayClient
from insurance_harness.compiler.pipeline import ExtractionPipeline, PipelineConfig
from insurance_harness.compiler.prompts import (
    GAPFILL_SYSTEM,
    SEMANTIC_RESOLUTION_SYSTEM,
    VOTE_VARIANT_SUFFIXES,
)
from insurance_harness.compiler.sections import family_fingerprint, split_sections
from insurance_harness.compiler.templates import (
    ExtractionTemplate,
    FieldAnchors,
    InducedFrom,
    TableAnchor,
    TableGrid,
    TemplateField,
    TemplateRegistry,
    run_fastpath,
)
from insurance_harness.goldenset.pdf import PageText
from insurance_harness.schemas import FieldSpec, ProductLineSchema, SchemaRegistry
from insurance_harness.sources import DirectoryDocumentSource, DirectorySourceRequest

RATE_PAGES = [
    PageText(
        page_no=1,
        text=(
            "《测试终身寿险》年交费率表\n（每万元基本保险金额）\n"
            "交费期间\n趸交 3年 6年\n投保年龄\n0 100 50 30\n"
            "本产品犹豫期为20日，投保人签收合同之日起交费计算。"
        ),
    )
]
GRID = TableGrid(
    rows=(("交费期间\n投保年龄", "趸交", "3年", "6年"), ("0", "100", "50", "30"))
)

FIELDS = (
    # 交费期限设为 high：验证 fastpath 字段退出投票（F3.4）
    FieldSpec(name="交费期限", field_id="pay_term", risk_level="high", source_sheet="t"),
    FieldSpec(name="犹豫期", field_id="hesitation_period", source_sheet="t"),
)
LINE = ProductLineSchema(line_key="t", sheet_name="测试", fields=FIELDS)
REGISTRY = SchemaRegistry(version="v1.1+fastpathtest", lines={"t": LINE}, glossary=())
FIELDS_BY_ID = {f.field_id: f for f in FIELDS}

FAMILY = family_fingerprint(split_sections(RATE_PAGES))


def _template(anchors: FieldAnchors, status: str = "published") -> ExtractionTemplate:
    return ExtractionTemplate(
        template_id="tpl-test-费率表",
        family_id=FAMILY,
        doc="费率表.pdf",
        status=status,  # type: ignore[arg-type]
        induced_from=InducedFrom(products=("产品A", "产品B"), golden_release="wip"),
        fields=(
            TemplateField(field_id="pay_term", field_name="交费期限", anchors=anchors),
        ),
    )


class FakeProvider:
    def __init__(self, grids: list[TableGrid]) -> None:
        self._grids = grids
        self.calls = 0

    def extract_tables(self, pdf_path: Path, page_no: int) -> list[TableGrid]:
        self.calls += 1
        return self._grids if page_no == 1 else []


TABLE_ANCHORS = FieldAnchors(
    pages=(1,), table_columns=TableAnchor(op="join_headers", header_contains="趸交")
)


def test_f3_1_table_anchor_deterministic_extraction() -> None:
    cands = run_fastpath(
        _template(TABLE_ANCHORS),
        FIELDS_BY_ID,
        "费率表.pdf",
        RATE_PAGES,
        pdf_path=Path("/fake/费率表.pdf"),
        provider=FakeProvider([GRID]),
    )
    assert len(cands) == 1
    c = cands[0]
    assert c.value == "趸交、3年、6年" and c.tri_state == "present"
    assert c.origin == "fastpath" and c.confidence == "high"
    assert c.evidence[0].page == 1
    assert c.metadata["data_quality"] == "table_parsed"


def test_f3_1_regex_anchor_extraction_with_page_hint_tolerance() -> None:
    anchors = FieldAnchors(pages=(2,), regex=r"本产品犹豫期为(\d+日)")  # 提示页 ±1 容忍
    template = _template(anchors).model_copy(
        update={
            "fields": (
                TemplateField(
                    field_id="hesitation_period", field_name="犹豫期", anchors=anchors
                ),
            )
        }
    )
    cands = run_fastpath(template, FIELDS_BY_ID, "费率表.pdf", RATE_PAGES)
    assert len(cands) == 1
    assert cands[0].value == "20日"
    assert cands[0].metadata["data_quality"] == "structured_direct"
    # 页提示范围外 → 锚点未命中 → 降级（无候选）
    far = template.model_copy(
        update={
            "fields": (
                TemplateField(
                    field_id="hesitation_period",
                    field_name="犹豫期",
                    anchors=FieldAnchors(pages=(9,), regex=r"本产品犹豫期为(\d+日)"),
                ),
            )
        }
    )
    assert run_fastpath(far, FIELDS_BY_ID, "费率表.pdf", RATE_PAGES) == []


def test_f3_2_validation_chain_rejects_unverifiable_quote() -> None:
    """表格 provider 给出的列名不在页面原文（解析漂移）→ 回验失败 → 丢弃降级。"""
    ghost = FakeProvider(
        [TableGrid(rows=(("期间", "月交", "季交", "半年交"), ("0", "1", "2", "3")))]
    )
    cands = run_fastpath(
        _template(FieldAnchors(table_columns=TableAnchor(header_contains="月交"))),
        FIELDS_BY_ID,
        "费率表.pdf",
        RATE_PAGES,
        pdf_path=Path("/fake/费率表.pdf"),
        provider=ghost,
    )
    assert cands == []  # 不是 unknown——通用管道仍会抽该字段（F3.2）


def test_f3_3_no_provider_or_anchor_miss_degrades() -> None:
    # 表格锚点但无 provider → 降级
    assert (
        run_fastpath(_template(TABLE_ANCHORS), FIELDS_BY_ID, "费率表.pdf", RATE_PAGES) == []
    )
    # 模板字段不在 schema → 忽略
    other = _template(TABLE_ANCHORS).model_copy(
        update={
            "fields": (
                TemplateField(
                    field_id="ghost_field", field_name="不存在", anchors=TABLE_ANCHORS
                ),
            )
        }
    )
    assert (
        run_fastpath(
            other, FIELDS_BY_ID, "费率表.pdf", RATE_PAGES,
            pdf_path=Path("/f.pdf"), provider=FakeProvider([GRID]),
        )
        == []
    )


# --- 管道集成（F3.4/F3.5） ---


class ScriptedClient:
    """规则化假弱模型：只会答犹豫期；记录全部 prompt 供成本断言。"""

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.prompts.append(system + "\n" + user)
        fids = re.findall(r"field_id=(\w+)", user)
        items = []
        for fid in fids:
            if fid == "pay_term" and "趸交" in user:
                items.append(
                    {
                        "field_id": fid,
                        "value": "趸交、3年、6年",
                        "tri_state": "present",
                        "evidence": [{"page": 1, "quote": "趸交 3年 6年"}],
                    }
                )
            elif fid == "hesitation_period" and "犹豫期" in user:
                items.append(
                    {
                        "field_id": fid,
                        "value": "20日",
                        "tri_state": "present",
                        "evidence": [{"page": 1, "quote": "犹豫期为20日"}],
                    }
                )
            else:
                items.append(
                    {"field_id": fid, "value": None, "tri_state": "unknown", "evidence": []}
                )
        return json.dumps(items, ensure_ascii=False)


def _make_product_dir(tmp_path: Path) -> Path:
    product_dir = tmp_path / "测试终身寿险产品"
    product_dir.mkdir()
    (product_dir / "费率表.pdf").touch()  # 占位；页面由 page_loader 注入
    (product_dir / "product_meta.json").write_text(
        json.dumps({"planCode": "TEST06"}), encoding="utf-8"
    )
    return product_dir


async def _fast_sleep(_: float) -> None:
    return None


def _pipeline(
    client: ScriptedClient | ReplayClient, registry_templates: TemplateRegistry | None
) -> ExtractionPipeline:
    return ExtractionPipeline(
        client=client,
        registry=REGISTRY,
        model_id="scripted-test",
        source=DirectoryDocumentSource(
            replay_identity="template-fastpath-test",
            parser_fingerprint="fixture-parser-v1",
            page_loader=lambda _: list(RATE_PAGES),
        ),
        config=PipelineConfig(
            concurrency=2,
            transport_attempts=2,
            backoff_base_s=0.0,
            model_profile="offline-eval",
        ),
        sleep=_fast_sleep,
        template_registry=registry_templates,
        table_provider=FakeProvider([GRID]),
    )


async def test_f3_4_f3_5_pipeline_fastpath_end_to_end(tmp_path: Path) -> None:
    template_registry = TemplateRegistry(
        version="tpl-v1+test", templates=(_template(TABLE_ANCHORS),)
    )
    client = ScriptedClient()
    product_dir = _make_product_dir(tmp_path)
    result = await _pipeline(client, template_registry).run(
        product_dir=product_dir,
        source_request=DirectorySourceRequest(product_dir=product_dir),
        run_dir=tmp_path / "run",
        line_key="t",
    )
    by_id = {r.field_id: r for r in result.records}

    # Mission 136：模板只提供候选，最终字段由 LLM 选择并通过回验。
    pay = by_id["pay_term"]
    assert pay.tri_state == "present" and pay.value == "趸交、3年、6年"
    assert pay.data_quality == "llm_extracted" and pay.confidence == "medium"
    # 通用管道字段不受影响，data_quality 默认 llm_extracted
    hes = by_id["hesitation_period"]
    assert hes.tri_state == "present" and hes.data_quality == "llm_extracted"

    # Mission 136：规则候选不再直接出场，必须进入一次 LLM 语义裁决；
    # 语义裁决成功后才退出通用抽取/补漏/投票。
    assert any(SEMANTIC_RESOLUTION_SYSTEM in p and "pay_term" in p for p in client.prompts)
    assert not any(
        s in p for p in client.prompts for s in VOTE_VARIANT_SUFFIXES
    ), "fastpath 高风险字段不得进入投票采样"
    assert not any(GAPFILL_SYSTEM in p for p in client.prompts)

    # manifest 记录（F3/F4.2）
    m = result.manifest
    assert m.fastpath_fields == 1 and m.template_registry_version == "tpl-v1+test"
    assert m.docs[0].fastpath_fields == 1
    assert 0.0 <= m.docs[0].feedability_score <= 1.0

    # pred JSONL 行含 data_quality 字段（007 导入器留位）
    row = json.loads(result.pred_path.read_text(encoding="utf-8").splitlines()[0])
    assert "data_quality" in row


async def test_f3_3_without_registry_behavior_unchanged(tmp_path: Path) -> None:
    client = ScriptedClient()
    product_dir = _make_product_dir(tmp_path)
    result = await _pipeline(client, None).run(
        product_dir=product_dir,
        source_request=DirectorySourceRequest(product_dir=product_dir),
        run_dir=tmp_path / "run",
        line_key="t",
    )
    by_id = {r.field_id: r for r in result.records}
    assert by_id["pay_term"].tri_state == "unknown"  # 无模板 → 通用管道（模型不会答）
    assert by_id["pay_term"].data_quality == "llm_extracted"
    assert result.manifest.fastpath_fields == 0
    assert result.manifest.template_registry_version == ""
    assert any("pay_term" in p for p in client.prompts)  # 字段照常进通用抽取
