from __future__ import annotations

from threading import Barrier, Event, Lock
from types import SimpleNamespace

import httpx
import pytest

from insurance_harness.v5_preview import m158_run
from insurance_harness.v5_preview.llm_plugin import CompletionReceipt
from insurance_harness.v5_preview.m154_concurrency import (
    AdaptiveProviderGate,
    BatchConcurrencyProfile,
    GlobalCallBudget,
    invoke_provider_attempt,
)
from insurance_harness.v5_preview.m156_run import M156Material


def test_eight_batches_overlap_with_isolated_receipts_and_stable_merge(monkeypatch) -> None:
    barrier = Barrier(8, timeout=10)
    last_batch_finished = Event()
    lock = Lock()
    clients = []
    completion_order = []
    frozen_preview = object()
    product = SimpleNamespace(preview=frozen_preview, product_version_id="596-1")
    batches = tuple(
        m158_run.M158Batch(index, (f"field-{index}",), str(index), "compact_coupled", {})
        for index in range(1, 9)
    )

    class Client:
        def __init__(self) -> None:
            self.receipts = []
            self.closed = False
            with lock:
                clients.append(self)

        def close(self) -> None:
            self.closed = True

    def extract(*, completion, context, preview, **kwargs):
        assert preview is frozen_preview
        assert not completion.closed
        barrier.wait()
        if context != "8":
            assert last_batch_finished.wait(10)
        completion.receipts.append(CompletionReceipt(
            response_id=f"response-{context}", response_model="test", finish_reason="stop",
        ))
        with lock:
            completion_order.append(int(context))
        if context == "8":
            last_batch_finished.set()
        return (context,)

    monkeypatch.setattr(m158_run, "_execute_batch", extract)
    profile = BatchConcurrencyProfile(max_batches=8)
    gate = AdaptiveProviderGate(profile)
    budget = GlobalCallBudget(total_calls=8, required_primary_calls=8)
    outputs = m158_run._execute_planned_batches(
        product=product,
        material=M156Material((), 0, ()),
        batches=batches,
        completion_factory=Client,
        budget=budget,
        gate=gate,
        policy=m158_run.M158RunPolicy.default(),
        profile=profile,
    )

    assert gate.peak_active == 8
    assert completion_order[0] == 8
    assert [item.batch.batch_index for item in outputs] == list(range(1, 9))
    assert [item.results for item in outputs] == [(str(i),) for i in range(1, 9)]
    assert [item.calls[0].completion.response_id for item in outputs] == [
        f"response-{i}" for i in range(1, 9)
    ]
    assert sorted(item.calls[0].provider_call for item in outputs) == list(range(1, 9))
    assert all(item.timings[0].started_at and item.timings[0].finished_at for item in outputs)
    assert len(clients) == 8 and all(client.closed for client in clients)


@pytest.mark.parametrize("retry_budget", [0, 1])
def test_failed_batch_cannot_consume_other_batches_primary_budget(
    monkeypatch, retry_budget,
) -> None:
    attempts = {}

    class Client:
        receipts = ()

        def close(self) -> None:
            pass

    def extract(*, context, **kwargs):
        attempts[context] = attempts.get(context, 0) + 1
        if context == "1" and attempts[context] == 1:
            raise ValueError("malformed provider result")
        return (context,)

    monkeypatch.setattr(m158_run, "_execute_batch", extract)
    profile = BatchConcurrencyProfile(max_batches=1)
    budget = GlobalCallBudget(total_calls=3 + retry_budget, required_primary_calls=3)
    outputs = m158_run._execute_planned_batches(
        product=SimpleNamespace(preview=object(), product_version_id="596-1"),
        material=M156Material((), 0, ()),
        batches=tuple(
            m158_run.M158Batch(i, (f"field-{i}",), str(i), "compact_coupled", {})
            for i in range(1, 4)
        ),
        completion_factory=Client,
        budget=budget,
        gate=AdaptiveProviderGate(profile),
        policy=m158_run.M158RunPolicy.default(),
        profile=profile,
    )
    assert attempts == {"1": 1 + retry_budget, "2": 1, "3": 1}
    assert outputs[0].results == (("1",) if retry_budget else None)
    assert outputs[1].results == ("2",)
    assert outputs[2].results == ("3",)
    assert budget.used == 3 + retry_budget


def test_eight_way_gate_records_429_and_reduces_future_admissions() -> None:
    gate = AdaptiveProviderGate(BatchConcurrencyProfile(max_batches=8))
    request = httpx.Request("POST", "https://provider.invalid/chat/completions")
    error = httpx.HTTPStatusError(
        "limited", request=request, response=httpx.Response(429, request=request),
    )

    def fail():
        raise error

    outcome = invoke_provider_attempt(
        budget=GlobalCallBudget(total_calls=1, required_primary_calls=1),
        gate=gate, product_version_id="596-1", batch_index=1, attempt=1, retry=False, call=fail,
    )
    assert outcome.error is error
    assert gate.current_limit == 2
    assert [(event.from_limit, event.to_limit) for event in gate.throttle_events] == [(8, 2)]
