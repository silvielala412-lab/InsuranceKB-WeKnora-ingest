from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

import httpx
import pytest
from pydantic import ValidationError

from insurance_harness.v5_preview.m154_concurrency import (
    AdaptiveProviderGate,
    CallBudgetExhausted,
    GlobalCallBudget,
    ProductConcurrencyProfile,
    ProductWork,
    RunTimingRecorder,
    execute_products_ordered,
    invoke_provider_attempt,
)


def _rate_limit_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.invalid/chat/completions")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("rate limited", request=request, response=response)


def test_capacity_profile_is_closed_and_bounded_to_four_products() -> None:
    assert ProductConcurrencyProfile().max_products == 4
    assert ProductConcurrencyProfile(max_products=1).max_products == 1
    with pytest.raises(ValidationError):
        ProductConcurrencyProfile(max_products=0)
    with pytest.raises(ValidationError):
        ProductConcurrencyProfile(max_products=5)
    with pytest.raises(ValidationError):
        ProductConcurrencyProfile(max_products=4, product_limit=8)  # type: ignore[call-arg]


def test_products_run_four_way_but_batches_remain_serial_per_product() -> None:
    works = tuple(
        ProductWork(ordinal=index, product_version_id=f"product-{index}", payload=(1, 2, 3))
        for index in range(8)
    )
    profile = ProductConcurrencyProfile(max_products=4)
    gate = AdaptiveProviderGate(profile)
    budget = GlobalCallBudget(total_calls=24, required_primary_calls=24)
    lock = Lock()
    active_by_product: defaultdict[str, int] = defaultdict(int)
    peak_by_product: defaultdict[str, int] = defaultdict(int)

    def worker(work: ProductWork[tuple[int, ...]]) -> str:
        for batch_index in work.payload:
            def call(current_batch_index: int = batch_index) -> str:
                with lock:
                    active_by_product[work.product_version_id] += 1
                    peak_by_product[work.product_version_id] = max(
                        peak_by_product[work.product_version_id],
                        active_by_product[work.product_version_id],
                    )
                sleep(0.01)
                with lock:
                    active_by_product[work.product_version_id] -= 1
                return f"{work.product_version_id}:{current_batch_index}"

            outcome = invoke_provider_attempt(
                budget=budget,
                gate=gate,
                product_version_id=work.product_version_id,
                batch_index=batch_index,
                attempt=1,
                retry=False,
                call=call,
            )
            assert outcome.error is None
        return work.product_version_id

    result = execute_products_ordered(works, worker=worker, profile=profile)

    assert result.values == tuple(f"product-{index}" for index in range(8))
    assert result.peak_products == 4
    assert gate.peak_active == 4
    assert set(peak_by_product.values()) == {1}
    assert budget.used == 24


def test_global_budget_is_atomic_and_reserves_primary_calls_before_retries() -> None:
    budget = GlobalCallBudget(total_calls=7, required_primary_calls=6)

    def reserve_primary(index: int) -> int:
        return budget.reserve_primary(f"p-{index}", 1, 1).provider_call

    with ThreadPoolExecutor(max_workers=6) as pool:
        calls = tuple(pool.map(reserve_primary, range(6)))

    retry = budget.reserve_retry("p-0", 1, 2)
    assert retry is not None
    assert sorted((*calls, retry.provider_call)) == list(range(1, 8))
    assert budget.reserve_retry("p-1", 1, 2) is None
    with pytest.raises(CallBudgetExhausted):
        budget.reserve_primary("extra", 1, 1)
    assert budget.used == 7


def test_http_429_downgrades_future_provider_concurrency_four_to_two_to_one() -> None:
    profile = ProductConcurrencyProfile(max_products=4)
    gate = AdaptiveProviderGate(profile)
    budget = GlobalCallBudget(total_calls=3, required_primary_calls=3)

    first = invoke_provider_attempt(
        budget=budget,
        gate=gate,
        product_version_id="p-1",
        batch_index=1,
        attempt=1,
        retry=False,
        call=lambda: (_ for _ in ()).throw(_rate_limit_error()),
    )
    second = invoke_provider_attempt(
        budget=budget,
        gate=gate,
        product_version_id="p-2",
        batch_index=1,
        attempt=1,
        retry=False,
        call=lambda: (_ for _ in ()).throw(_rate_limit_error()),
    )
    third = invoke_provider_attempt(
        budget=budget,
        gate=gate,
        product_version_id="p-3",
        batch_index=1,
        attempt=1,
        retry=False,
        call=lambda: "ok",
    )

    assert isinstance(first.error, httpx.HTTPStatusError)
    assert isinstance(second.error, httpx.HTTPStatusError)
    assert third.value == "ok"
    assert gate.current_limit == 1
    assert tuple((event.from_limit, event.to_limit) for event in gate.throttle_events) == (
        (4, 2),
        (2, 1),
    )


def test_out_of_order_completion_has_stable_product_merge() -> None:
    works = tuple(
        ProductWork(ordinal=index, product_version_id=f"p-{index}", payload=index)
        for index in range(6)
    )

    def worker(work: ProductWork[int]) -> str:
        sleep((5 - work.payload) * 0.002)
        return f"result-{work.payload}"

    serial = execute_products_ordered(
        works,
        worker=worker,
        profile=ProductConcurrencyProfile(max_products=1),
    )
    parallel = execute_products_ordered(
        works,
        worker=worker,
        profile=ProductConcurrencyProfile(max_products=4),
    )

    assert parallel.values == serial.values
    assert parallel.values == tuple(f"result-{index}" for index in range(6))
    assert parallel.completion_order != tuple(work.product_version_id for work in works)


def test_stage_timing_contract_covers_complete_run_and_provider_attempts() -> None:
    timer = RunTimingRecorder()
    with timer.stage("materials_parse"):
        sleep(0.001)
    with timer.stage("planning"):
        sleep(0.001)
    with timer.stage("provider"):
        sleep(0.001)
    with timer.stage("merge_write"):
        sleep(0.001)

    receipt = timer.finish(
        peak_product_workers=4,
        peak_provider_calls=3,
        product_timings=(),
        provider_attempts=(),
        throttle_events=(),
    )

    assert tuple(stage.name for stage in receipt.stages) == (
        "materials_parse",
        "planning",
        "provider",
        "merge_write",
    )
    assert all(stage.duration_ms > 0 for stage in receipt.stages)
    assert receipt.total_ms >= sum(stage.duration_ms for stage in receipt.stages)
    assert receipt.peak_product_workers == 4
    assert receipt.peak_provider_calls == 3
