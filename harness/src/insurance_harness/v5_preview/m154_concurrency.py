from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Condition, Lock
from time import perf_counter
from typing import Annotated, Literal, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

StageName = Literal["materials_parse", "planning", "provider", "merge_write"]
_STAGE_ORDER: tuple[StageName, ...] = (
    "materials_parse",
    "planning",
    "provider",
    "merge_write",
)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProductConcurrencyProfile(_ClosedModel):
    max_products: Annotated[int, Field(ge=1, le=4)] = 4


class BatchConcurrencyProfile(_ClosedModel):
    contract: Literal["insurance-v5-batch-concurrency.v1"] = (
        "insurance-v5-batch-concurrency.v1"
    )
    max_batches: Annotated[int, Field(ge=1, le=8)] = 1


class CallReservation(_ClosedModel):
    provider_call: Annotated[int, Field(ge=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    batch_index: Annotated[int, Field(ge=1)]
    attempt: Annotated[int, Field(ge=1)]
    kind: Literal["primary", "retry"]


class ProviderThrottleEvent(_ClosedModel):
    provider_call: Annotated[int, Field(ge=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    batch_index: Annotated[int, Field(ge=1)]
    from_limit: Annotated[int, Field(ge=2, le=8)]
    to_limit: Annotated[int, Field(ge=1, le=2)]
    reason: Literal["HTTP_429"] = "HTTP_429"


class StageTimingReceipt(_ClosedModel):
    name: StageName
    duration_ms: Annotated[float, Field(ge=0)]


class ProductTimingReceipt(_ClosedModel):
    ordinal: Annotated[int, Field(ge=0)]
    product_version_id: Annotated[str, Field(min_length=1)]
    duration_ms: Annotated[float, Field(ge=0)]


class ProviderAttemptTiming(_ClosedModel):
    provider_call: Annotated[int, Field(ge=1)]
    product_version_id: Annotated[str, Field(min_length=1)]
    batch_index: Annotated[int, Field(ge=1)]
    attempt: Annotated[int, Field(ge=1)]
    gate_wait_ms: Annotated[float, Field(ge=0)]
    duration_ms: Annotated[float, Field(ge=0)]
    outcome: Literal["ACCEPTED", "ERROR"]
    started_at: str = ""
    finished_at: str = ""


class M154RunTimingReceipt(_ClosedModel):
    contract: Literal["insurance-v5-m154-run-timing.v1"] = (
        "insurance-v5-m154-run-timing.v1"
    )
    started_at: Annotated[str, Field(min_length=1)]
    finished_at: Annotated[str, Field(min_length=1)]
    total_ms: Annotated[float, Field(ge=0)]
    stages: Annotated[tuple[StageTimingReceipt, ...], Field(min_length=4, max_length=4)]
    peak_product_workers: Annotated[int, Field(ge=0, le=4)]
    peak_provider_calls: Annotated[int, Field(ge=0, le=8)]
    product_timings: tuple[ProductTimingReceipt, ...]
    provider_attempts: tuple[ProviderAttemptTiming, ...]
    throttle_events: tuple[ProviderThrottleEvent, ...]


class CallBudgetExhausted(RuntimeError):
    pass


class RetryBudgetUnavailable(RuntimeError):
    pass


class GlobalCallBudget:
    """Atomically assigns attempt numbers while protecting unstarted primary calls."""

    def __init__(self, *, total_calls: int, required_primary_calls: int) -> None:
        if total_calls < 1 or not 0 <= required_primary_calls <= total_calls:
            raise ValueError("M154_CALL_BUDGET_INVALID")
        self._total_calls = total_calls
        self._remaining_primary_calls = required_primary_calls
        self._used = 0
        self._lock = Lock()

    def reserve_primary(
        self,
        product_version_id: str,
        batch_index: int,
        attempt: int,
    ) -> CallReservation:
        with self._lock:
            if self._remaining_primary_calls <= 0 or self._used >= self._total_calls:
                raise CallBudgetExhausted("M154_PRIMARY_CALL_BUDGET_EXHAUSTED")
            self._used += 1
            self._remaining_primary_calls -= 1
            provider_call = self._used
        return CallReservation(
            provider_call=provider_call,
            product_version_id=product_version_id,
            batch_index=batch_index,
            attempt=attempt,
            kind="primary",
        )

    def reserve_retry(
        self,
        product_version_id: str,
        batch_index: int,
        attempt: int,
    ) -> CallReservation | None:
        with self._lock:
            available = self._total_calls - self._used
            if available <= self._remaining_primary_calls:
                return None
            self._used += 1
            provider_call = self._used
        return CallReservation(
            provider_call=provider_call,
            product_version_id=product_version_id,
            batch_index=batch_index,
            attempt=attempt,
            kind="retry",
        )

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return self._total_calls - self._used


@dataclass(frozen=True, slots=True)
class GateAdmission:
    wait_ms: float


class AdaptiveProviderGate:
    """Limits simultaneous calls and lowers the limit after exact HTTP 429 responses."""

    def __init__(self, profile: ProductConcurrencyProfile | BatchConcurrencyProfile) -> None:
        self._limit = (
            profile.max_batches if isinstance(profile, BatchConcurrencyProfile)
            else profile.max_products
        )
        self._active = 0
        self._peak_active = 0
        self._condition = Condition()
        self._events: list[ProviderThrottleEvent] = []

    @contextmanager
    def slot(self) -> Iterator[GateAdmission]:
        waiting_since = perf_counter()
        with self._condition:
            while self._active >= self._limit:
                self._condition.wait()
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)
        admission = GateAdmission(wait_ms=_milliseconds(perf_counter() - waiting_since))
        try:
            yield admission
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()

    def report_rate_limit(self, reservation: CallReservation) -> None:
        with self._condition:
            if self._limit <= 1:
                return
            from_limit = self._limit
            self._limit = 2 if self._limit > 2 else 1
            self._events.append(
                ProviderThrottleEvent(
                    provider_call=reservation.provider_call,
                    product_version_id=reservation.product_version_id,
                    batch_index=reservation.batch_index,
                    from_limit=from_limit,
                    to_limit=self._limit,
                )
            )
            self._condition.notify_all()

    @property
    def current_limit(self) -> int:
        with self._condition:
            return self._limit

    @property
    def peak_active(self) -> int:
        with self._condition:
            return self._peak_active

    @property
    def throttle_events(self) -> tuple[ProviderThrottleEvent, ...]:
        with self._condition:
            return tuple(self._events)


@dataclass(frozen=True, slots=True)
class ProviderAttemptOutcome[R]:
    reservation: CallReservation
    value: R | None
    error: Exception | None
    timing: ProviderAttemptTiming


def invoke_provider_attempt[R](
    *,
    budget: GlobalCallBudget,
    gate: AdaptiveProviderGate,
    product_version_id: str,
    batch_index: int,
    attempt: int,
    retry: bool,
    call: Callable[[], R],
) -> ProviderAttemptOutcome[R]:
    reservation = (
        budget.reserve_retry(product_version_id, batch_index, attempt)
        if retry
        else budget.reserve_primary(product_version_id, batch_index, attempt)
    )
    if reservation is None:
        raise RetryBudgetUnavailable("M154_RETRY_BUDGET_UNAVAILABLE")
    started_at = _utc_now()
    started = perf_counter()
    value: R | None = None
    error: Exception | None = None
    with gate.slot() as admission:
        try:
            value = call()
        except Exception as exc:  # The caller decides which typed failures are admissible.
            error = exc
            if _is_http_429(exc):
                gate.report_rate_limit(reservation)
    timing = ProviderAttemptTiming(
        provider_call=reservation.provider_call,
        product_version_id=product_version_id,
        batch_index=batch_index,
        attempt=attempt,
        gate_wait_ms=admission.wait_ms,
        duration_ms=_milliseconds(perf_counter() - started),
        outcome="ERROR" if error is not None else "ACCEPTED",
        started_at=started_at,
        finished_at=_utc_now(),
    )
    return ProviderAttemptOutcome(
        reservation=reservation,
        value=value,
        error=error,
        timing=timing,
    )


@dataclass(frozen=True, slots=True)
class ProductWork[T]:
    ordinal: int
    product_version_id: str
    payload: T


@dataclass(frozen=True, slots=True)
class OrderedProductExecution[R]:
    values: tuple[R, ...]
    completion_order: tuple[str, ...]
    peak_products: int
    product_timings: tuple[ProductTimingReceipt, ...]
    duration_ms: float


def execute_products_ordered[T, R](
    works: Sequence[ProductWork[T]],
    *,
    worker: Callable[[ProductWork[T]], R],
    profile: ProductConcurrencyProfile,
) -> OrderedProductExecution[R]:
    if tuple(sorted(work.ordinal for work in works)) != tuple(range(len(works))):
        raise ValueError("M154_PRODUCT_ORDINALS_INVALID")
    if len({work.product_version_id for work in works}) != len(works):
        raise ValueError("M154_PRODUCT_VERSION_DUPLICATED")
    started = perf_counter()
    lock = Lock()
    active = 0
    peak = 0
    completion_order: list[str] = []
    timings: dict[int, ProductTimingReceipt] = {}
    results: list[R | None] = [None] * len(works)

    def observed(work: ProductWork[T]) -> R:
        nonlocal active, peak
        product_started = perf_counter()
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            return worker(work)
        finally:
            duration_ms = _milliseconds(perf_counter() - product_started)
            with lock:
                active -= 1
                completion_order.append(work.product_version_id)
                timings[work.ordinal] = ProductTimingReceipt(
                    ordinal=work.ordinal,
                    product_version_id=work.product_version_id,
                    duration_ms=duration_ms,
                )

    with ThreadPoolExecutor(max_workers=profile.max_products) as pool:
        futures = {pool.submit(observed, work): work for work in works}
        for future in as_completed(futures):
            work = futures[future]
            results[work.ordinal] = future.result()

    if any(result is None for result in results):
        raise RuntimeError("M154_PRODUCT_RESULT_MISSING")
    return OrderedProductExecution(
        values=tuple(cast(R, result) for result in results),
        completion_order=tuple(completion_order),
        peak_products=peak,
        product_timings=tuple(timings[index] for index in range(len(works))),
        duration_ms=_milliseconds(perf_counter() - started),
    )


class RunTimingRecorder:
    def __init__(self) -> None:
        self._started_at = _utc_now()
        self._started = perf_counter()
        self._stages: dict[StageName, float] = {}

    @contextmanager
    def stage(self, name: StageName) -> Iterator[None]:
        if name in self._stages:
            raise ValueError("M154_STAGE_RECORDED_TWICE")
        started = perf_counter()
        yield
        self._stages[name] = _milliseconds(perf_counter() - started)

    def finish(
        self,
        *,
        peak_product_workers: int,
        peak_provider_calls: int,
        product_timings: Sequence[ProductTimingReceipt],
        provider_attempts: Sequence[ProviderAttemptTiming],
        throttle_events: Sequence[ProviderThrottleEvent],
    ) -> M154RunTimingReceipt:
        if set(self._stages) != set(_STAGE_ORDER):
            raise ValueError("M154_STAGE_TIMING_INCOMPLETE")
        stages = tuple(
            StageTimingReceipt(name=name, duration_ms=self._stages[name])
            for name in _STAGE_ORDER
        )
        measured_total = _milliseconds(perf_counter() - self._started)
        total_ms = max(measured_total, sum(stage.duration_ms for stage in stages))
        return M154RunTimingReceipt(
            started_at=self._started_at,
            finished_at=_utc_now(),
            total_ms=total_ms,
            stages=stages,
            peak_product_workers=peak_product_workers,
            peak_provider_calls=peak_provider_calls,
            product_timings=tuple(product_timings),
            provider_attempts=tuple(provider_attempts),
            throttle_events=tuple(throttle_events),
        )

    @property
    def started_at(self) -> str:
        return self._started_at


def _is_http_429(error: Exception) -> bool:
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429


def _milliseconds(seconds: float) -> float:
    return round(seconds * 1_000, 3)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "AdaptiveProviderGate",
    "BatchConcurrencyProfile",
    "CallBudgetExhausted",
    "CallReservation",
    "GlobalCallBudget",
    "M154RunTimingReceipt",
    "OrderedProductExecution",
    "ProductConcurrencyProfile",
    "ProductTimingReceipt",
    "ProductWork",
    "ProviderAttemptOutcome",
    "ProviderAttemptTiming",
    "ProviderThrottleEvent",
    "RetryBudgetUnavailable",
    "RunTimingRecorder",
    "execute_products_ordered",
    "invoke_provider_attempt",
]
