"""Product-scoped rule supplements for non-serving V5 candidate previews."""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence

from .contracts import FieldDefinition, PluginFieldResult, V5CandidatePreview
from .full_schema_quality import audit_full_schema_candidate
from .ingest import preview_digest
from .m160_quality import admit_m160_evidence_subset
from .source_evidence import SourcePage
from .llm_plugin import CompletionPort, LlmPluginError


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def select_product_rule_pages(
    pages: Sequence[SourcePage], *, page_numbers: Sequence[int],
    product_id: str, product_display_name: str,
) -> tuple[SourcePage, ...]:
    """Keep original PDF page numbers and reject another product's section."""
    selected = tuple(page for page in pages if page.page_number in page_numbers)
    if not selected or tuple(page.page_number for page in selected) != tuple(page_numbers):
        raise ValueError("RULE_PAGE_SELECTION_INVALID")
    if len({(page.document_name, page.document_sha256) for page in selected}) != 1:
        raise ValueError("RULE_DOCUMENT_IDENTITY_MIXED")
    for index, page in enumerate(selected):
        text = _compact(page.text)
        if index == 0 or "本规则仅适用于" in text:
            scope = text.split("未涉及", 1)[0]
            if (
                "本规则仅适用于" not in scope
                or _compact(product_display_name) not in scope
                or not re.search(rf"(?<!\d){re.escape(product_id)}(?!\d)", scope)
            ):
                raise ValueError("RULE_PRODUCT_SCOPE_MISMATCH")
    return selected


def rebind_composite_preview(
    preview: V5CandidatePreview, *, source_revision_id: str,
) -> V5CandidatePreview:
    """Bind inherited evidence to a manifest that explicitly includes its parent.

    Evidence status is preserved, not upgraded. The caller must persist the
    parent manifest and new file/page scope in the composite manifest receipt.
    """
    payload = preview.model_dump(mode="json")
    payload.pop("preview_sha256")
    payload["source_revision_id"] = source_revision_id
    for field in payload["fields"]:
        for evidence in field["evidence"]:
            evidence["source_revision_id"] = source_revision_id
    return V5CandidatePreview.model_validate_json(
        json.dumps({**payload, "preview_sha256": preview_digest(payload)})
    )


def admit_supplemental_rule_field(
    definition: FieldDefinition, result: PluginFieldResult, *, candidate_text: str,
    product_display_name: str,
) -> tuple[PluginFieldResult | None, str]:
    """Admit source facts; keep schema-authorized synthesis as review content.

    Matching a source quote does not prove a generated summary's correctness.
    Synthesis is explicitly a candidate for review and cannot authorize serving.
    """
    if definition.field_id != result.field_id or definition.ordinal != result.ordinal:
        raise ValueError("RULE_FIELD_IDENTITY_MISMATCH")
    if result.state != "present":
        return None, "NO_NEW_SUPPORTED_VALUE"
    if not result.evidence or any(
        e.verification_status not in {"VERIFIED", "NORMALIZED_MATCH"}
        for e in result.evidence
    ):
        return None, "RULE_EVIDENCE_UNVERIFIED"
    if "LLM生成" in definition.formation_modes:
        return result, "SCHEMA_SYNTHESIS_REVIEW_REQUIRED"
    if definition.field_id in {"premium_payment_term", "premium_payment_frequency"}:
        accepted, decision = admit_m160_evidence_subset(
            result, candidate_text=candidate_text,
            product_display_name=product_display_name,
        )
        return accepted, decision.reason
    decision = audit_full_schema_candidate(
        field_id=result.field_id, proposed_value=result.value,
        evidence_quotes=tuple(e.quote for e in result.evidence),
        candidate_text=candidate_text,
    )
    # Reject incomplete arrays intact; do not replace a complete baseline with
    # a subset merely because a few returned items have literal source support.
    return (result if decision.accepted else None), decision.reason


class SourceBoundSynthesisCompletion:
    """Let synthesis select immutable source quotes instead of rewriting them.

    The regular plugin still validates topology, values and source evidence.
    This adapter is restricted to schema-authorized LLM synthesis fields.
    """
    def __init__(self, completion: CompletionPort, pages: Sequence[SourcePage]) -> None:
        self._completion = completion
        self.model = completion.model
        self._bank: dict[str, dict[str, str]] = {}
        for page in pages:
            for start in range(0, len(page.text), 1600):
                self._bank[f'Q{len(self._bank) + 1:03d}'] = {
                    'locator': f'pdf:{page.document_name}#page={page.page_number}',
                    'quote': page.text[start:start + 1800],
                }

    def complete(self, *, system: str, user: str) -> str:
        prompt = json.loads(user)
        if not prompt.get('schema_fields') or any(
            'LLM生成' not in f['formation_modes'] for f in prompt['schema_fields']
        ):
            raise LlmPluginError('SYNTHESIS_BANK_FIELD_MODE_INVALID')
        prompt['evidence_bank'] = self._bank
        prompt['source_text'] = '全部原文见evidence_bank；每个片段保留原始文件、页码和原文。'
        prompt['output_contract']['evidence_format'] = [{'evidence_id': 'Q001'}]
        instruction = (
            '\n本轮证据协议：fields中的evidence只返回[{"evidence_id":"Q001"}]这样的编号列表。'
            '从evidence_bank选择支撑本字段的片段，不输出locator或quote，不自行改写证据。'
            '其他字段结构和Schema要求不变。概括value允许改写，但业务条件必须完整准确。'
        )
        payload = json.loads(self._completion.complete(
            system=system + instruction, user=json.dumps(prompt, ensure_ascii=False),
        ))
        for field in payload['fields']:
            evidence = []
            for ref in field['evidence']:
                if not isinstance(ref, dict) or set(ref) != {'evidence_id'}:
                    raise LlmPluginError('SYNTHESIS_BANK_REFERENCE_INVALID')
                key = ref['evidence_id']
                if not isinstance(key, str) or key not in self._bank:
                    raise LlmPluginError('SYNTHESIS_BANK_REFERENCE_UNKNOWN')
                evidence.append(dict(self._bank[key]))
            field['evidence'] = evidence
        return json.dumps(payload, ensure_ascii=False)
