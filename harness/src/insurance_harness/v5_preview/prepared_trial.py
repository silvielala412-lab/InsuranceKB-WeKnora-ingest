"""Shared M160 planning and merging for already validated local product inputs."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from .contracts import PluginFieldResult, V5CandidatePreview
from .m156_run import M156Material
from .m158_run import M158Batch, M158RunPolicy, _field_record, _plan_product_batches
from .m160_run import material_backed_policy
from .provider_trial import ProviderTrialProduct


def prepared_material_policy(field_ids: tuple[str, ...], *, max_fields: int = 4) -> M158RunPolicy:
    return material_backed_policy(
        replace(
            M158RunPolicy.default(),
            focus_field_ids=field_ids,
            max_compact_fields=max_fields,
        )
    )


def plan_prepared_product(
    product: ProviderTrialProduct, material: M156Material, policy: M158RunPolicy
) -> tuple[M158Batch, ...]:
    return _plan_product_batches(product, material, policy=policy)


def merge_material_result(
    preview: V5CandidatePreview,
    result: PluginFieldResult,
    *,
    context: str,
    policy: M158RunPolicy,
    call: int,
    phase: str,
    batch: int = 0,
) -> tuple[V5CandidatePreview, dict[str, Any]]:
    admitted, decision = policy.evidence_admitter(
        result,
        candidate_text=context,
        product_display_name=preview.product_display_name,
    )
    proposal = admitted or PluginFieldResult(
        ordinal=result.ordinal, field_id=result.field_id, state="unknown"
    )
    # A partially supported proposal may fill a blank but must not narrow an
    # existing value. Keep the same baseline-preservation rule as e生保 preview.
    original = next(f for f in preview.fields if f.field_id == result.field_id)
    if decision.reason == "SOURCE_PARTIAL_EVIDENCE_ADMITTED" and original.state == "present":
        proposal = PluginFieldResult(
            ordinal=result.ordinal, field_id=result.field_id, state="unknown"
        )
    updated, record = _field_record(
        preview=preview,
        result=proposal,
        candidate_text=context,
        coverage={
            "admission": {
                "original_proposal": result.model_dump(mode="json"),
                "accepted": admitted is not None,
                "decision": asdict(decision),
            }
        },
        batch_index=batch,
        provider_call=call,
        phase=phase,
        replacement_selector=policy.replacement_selector,
    )
    return updated, asdict(record)
