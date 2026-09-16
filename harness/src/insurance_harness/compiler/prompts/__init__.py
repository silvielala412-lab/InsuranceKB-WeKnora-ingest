"""抽取管道 prompt 集中管理（spec E6.1：全部 prompt 在此、带版本常量）。

prompt 约定（04 Step 2）：模型只输出字段值 + 逐字引文 + 页码，禁止解释与原文复述
（原文由代码注入）；三态纪律硬约束（坑清单 #5：未抽取到 ≠ 不存在）。
字段级抽取指令（hint）来自 06 A8 的 FIELD_EXTRACTION_HINTS 资产思想。
"""

from collections.abc import Mapping, Sequence

from ...goldenset.pdf import PageText
from ...schemas import FieldSpec

PROMPT_VERSION = "ep-v1.0"
SEMANTIC_RESOLUTION_PROMPT_VERSION = "semantic-resolve-v1.0"

# --- 分批定向抽取（Step 2） ---

EXTRACTION_SYSTEM = """你是寿险产品文档信息抽取器。你收到文档节选（带页码）和一组字段定义，\
逐字段判定并只输出 JSON 数组，每个元素：
{"field_id": "...", "value": "字符串或 null", "tri_state": "present|absent_explicitly|unknown",
 "evidence": [{"page": 页码整数, "quote": "原文逐字摘录"}]}

严格规则：
- present：节选明确给出该字段取值。value 填简洁规范化取值；evidence 至少 1 条，
  quote 必须逐字来自对应页码的原文（程序会做字符串回验，任何改写都会作废）。
- absent_explicitly：节选明确表示不含/排除该项。也必须给 evidence。
- unknown：本节选中找不到依据。value 为 null，evidence 为空数组。
  禁止把"没找到"写成"无/不含"；禁止输出"未提及/详见条款"这类占位文字。
- 只依据本次给出的节选判断，不要引用节选之外的内容。
- 只输出 JSON 数组本身，不要任何解释、前后缀或代码围栏。"""

# --- 确定性候选的语义裁决 ---

SEMANTIC_RESOLUTION_SYSTEM = """你是寿险产品字段的语义裁决器。你会收到同一字段由规则、模板、\
产品主数据或不同文档位置产生的候选，以及候选页的原文上下文。请在候选之间按字段定义、\
产品身份和来源语义选择真正代表本字段的值；候选不准确时可以改用上下文中明确出现的\
原文值，但不能凭经验编造。

只输出一个 JSON 数组，恰好一个元素：
{"field_id":"...","doc":"文档名","value":"字符串或 null",\
"tri_state":"present|absent_explicitly|unknown",\
"evidence":[{"page":页码整数,"quote":"原文逐字摘录"}],"selected_candidate":整数或 null}

约束：
- present 或 absent_explicitly 必须有至少一条能在对应页逐字回验的 Evidence；
- unknown 表示现有候选和上下文不足以确定，不表示字段不存在；
- “以下简称”这类普通指代不能冒充正式的险种简称；
- 只使用本次给出的候选和原文上下文；不能输出解释、前后缀或代码围栏。"""

# --- 定向补漏：判断题式二次提问（Step 6） ---

GAPFILL_SYSTEM = """你是寿险产品文档核对器。你收到一个字段定义和一段候选原文（带页码），\
回答一道三选一判断题并只输出 JSON 数组（恰好一个元素）：
{"field_id": "...", "value": "字符串或 null", "tri_state": "present|absent_explicitly|unknown",
 "evidence": [{"page": 页码整数, "quote": "原文逐字摘录"}]}

判定：该段落是否说明本产品【包含该字段信息(present) / 明确不包含(absent_explicitly) / \
未提及(unknown)】？
- present 或 absent_explicitly 必须给出逐字引文（程序回验，改写作废）；
- 段落未提及时输出 unknown，禁止臆测；
- 只输出 JSON 数组本身。"""

# --- 高风险字段自一致性投票（Step 5）：3 个 prompt 变体产生独立采样 ---

VOTE_VARIANT_SUFFIXES: tuple[str, ...] = (
    "请直接判定该字段的取值。",
    "请先在心中把节选内容整理为“字段|取值|出处”表格，再输出该字段对应行的结论。",
    "请逐条核对节选中与该字段相关的条款表述后，输出最终结论。",
)

PARSE_RETRY_SUFFIX = "\n\n注意：上次输出无法解析为 JSON 数组。只输出 JSON 数组本身。"


def _field_line(f: FieldSpec) -> str:
    parts = [f"- field_id={f.field_id}｜字段名：{f.name}｜类型：{f.value_type}"]
    if f.description:
        parts.append(f"｜说明：{f.description}")
    if f.aliases:
        parts.append(f"｜别名：{'/'.join(f.aliases)}")
    return "".join(parts)


def render_fields(fields: Sequence[FieldSpec]) -> str:
    return "\n".join(_field_line(f) for f in fields)


def render_pages(fragments: Sequence[PageText]) -> str:
    return "\n\n".join(f"【第{f.page_no}页】\n{f.text}" for f in fragments)


def build_extraction_user(
    product_name: str,
    doc_name: str,
    fields: Sequence[FieldSpec],
    fragments: Sequence[PageText],
    feedback: str | None = None,
) -> str:
    user = (
        f"产品：{product_name}\n文档：{doc_name}\n\n"
        f"## 待抽取字段\n{render_fields(fields)}\n\n"
        f"## 文档节选（分页标注）\n{render_pages(fragments)}"
    )
    if feedback:
        user += f"\n\n## 上一轮问题（必须修正）\n{feedback}"
    return user


def build_semantic_resolution_user(
    product_name: str,
    field: FieldSpec,
    candidates: Sequence[object],
    pages_by_doc: Mapping[str, Sequence[PageText]],
) -> str:
    """组装候选裁决上下文；保留候选和页码，不把整本 PDF重复塞入请求。"""
    lines = [
        f"产品：{product_name}",
        f"字段：{_field_line(field)}",
        "",
        "## 候选值（编号从 0 开始）",
    ]
    context_keys: list[tuple[str, int]] = []
    for index, candidate in enumerate(candidates):
        doc = str(getattr(candidate, "doc", ""))
        value = getattr(candidate, "value", None)
        tri_state = getattr(candidate, "tri_state", "unknown")
        origin = getattr(candidate, "origin", "")
        evidence = getattr(candidate, "evidence", ()) or ()
        lines.append(
            f"候选 {index}：来源={origin}；文档={doc}；值={value!r}；状态={tri_state}"
        )
        for ev in evidence:
            page = int(getattr(ev, "page", 0))
            quote = str(getattr(ev, "quote", ""))
            lines.append(f"  Evidence：第{page}页｜{quote}")
            context_keys.append((doc, page))

    lines.extend(["", "## 候选页原文上下文"])
    rendered: set[tuple[str, int]] = set()
    for doc, page in context_keys:
        pages = pages_by_doc.get(doc, ())
        for fragment in pages:
            if abs(fragment.page_no - page) > 1:
                continue
            key = (doc, fragment.page_no)
            if key in rendered:
                continue
            rendered.add(key)
            lines.append(f"【文档：{doc}；第{fragment.page_no}页】\n{fragment.text}")
    if not rendered:
        lines.append("（没有可用的候选页上下文）")
    return "\n\n".join(lines)


def build_gapfill_user(
    product_name: str,
    doc_name: str,
    field: FieldSpec,
    fragments: Sequence[PageText],
    keywords: Sequence[str],
) -> str:
    return (
        f"产品：{product_name}\n文档：{doc_name}\n\n"
        f"## 待核对字段\n{_field_line(field)}\n"
        f"（检索关键词：{'、'.join(keywords)}）\n\n"
        f"## 候选原文（分页标注）\n{render_pages(fragments)}"
    )


def build_targeted_gapfill_user(
    product_name: str,
    doc_name: str,
    field: FieldSpec,
    fragments: Sequence[PageText],
    keywords: Sequence[str],
    guidance: str | None = None,
) -> str:
    """extract_empty 字段的定向二轮提问（024 E3.1，判断题/短答形态）。

    与 ``build_gapfill_user`` 同构（同一 GAPFILL_SYSTEM、同一回验契约，E3.2
    反幻觉门槛不降），追加定向指令块：短答优先、别名提示、可选值粒度指引
    （E4.1 经变体注入）。触发与组装均不接受任何金标输入（E3.1）。
    """
    lines = [
        "定向核对指令：",
        "- 优先给出短语级取值（日期/期限/金额/枚举原文短语），不要整段复述；",
        f"- 该字段亦可能以这些说法出现：{'、'.join(keywords)}；",
        '- 若段落仅给出指向他处的线索（如"详见附表"），输出 unknown。',
    ]
    if guidance:
        lines.append(f"- {guidance}")
    targeted_block = "\n".join(lines)
    return (
        f"产品：{product_name}\n文档：{doc_name}\n\n"
        f"## 待核对字段（定向补漏）\n{_field_line(field)}\n\n"
        f"{targeted_block}\n\n"
        f"## 候选原文（分页标注）\n{render_pages(fragments)}"
    )


def build_vote_user(
    product_name: str,
    doc_name: str,
    field: FieldSpec,
    fragments: Sequence[PageText],
    variant: int,
) -> str:
    return (
        f"产品：{product_name}\n文档：{doc_name}\n\n"
        f"## 待抽取字段\n{_field_line(field)}\n\n"
        f"## 文档节选（分页标注）\n{render_pages(fragments)}\n\n"
        f"{VOTE_VARIANT_SUFFIXES[variant % len(VOTE_VARIANT_SUFFIXES)]}"
    )
