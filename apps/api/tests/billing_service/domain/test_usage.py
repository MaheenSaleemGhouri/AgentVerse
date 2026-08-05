"""Usage recording rules and period folding."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentverse_api.billing_service.domain.plan import MeteredDimension
from agentverse_api.billing_service.domain.usage import (
    DIMENSION_SOURCES,
    LEVEL_DIMENSIONS,
    DimensionUsage,
    InvalidUsageError,
    PeriodUsage,
    UsageEvent,
    UsageSource,
    combine,
)

_T0 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _event(**overrides: object) -> UsageEvent:
    kwargs: dict[str, object] = {
        "workspace_id": "ws-1",
        "dimension": MeteredDimension.AGENT_RUNS,
        "quantity": 1,
        "occurred_at": _T0,
        "source": UsageSource.AGENT_RUN,
        "source_id": "run-1",
        "idempotency_key": "run:run-1:agent_runs",
    }
    kwargs.update(overrides)
    return UsageEvent(**kwargs)  # type: ignore[arg-type]


class TestDimensionSources:
    def test_every_metered_dimension_has_a_durable_source(self) -> None:
        # `saas-strategist`'s rule: a dimension with no source would have
        # its allowance always read as unused — a plan limit that
        # silently never applies.
        missing = set(MeteredDimension) - set(DIMENSION_SOURCES)
        assert not missing, f"no durable source declared for {missing}"

    def test_no_source_is_declared_for_a_dimension_that_does_not_exist(self) -> None:
        assert set(DIMENSION_SOURCES) <= set(MeteredDimension)


class TestEventValidation:
    def test_a_negative_quantity_is_refused(self) -> None:
        # Clamping to zero would hide the upstream bug while quietly
        # under-billing.
        with pytest.raises(InvalidUsageError, match="must not be negative"):
            _event(quantity=-1)

    def test_a_negative_cost_is_refused(self) -> None:
        with pytest.raises(InvalidUsageError):
            _event(cost_micro_usd=-1)

    def test_an_event_without_an_idempotency_key_is_refused(self) -> None:
        # Without one a retried worker bills the same work twice.
        with pytest.raises(InvalidUsageError, match="idempotency key"):
            _event(idempotency_key="")

    def test_zero_is_a_valid_quantity(self) -> None:
        # A run that used no tokens is a real, recordable fact.
        assert _event(quantity=0).quantity == 0


class TestCombine:
    def test_accumulating_dimensions_sum(self) -> None:
        assert combine(MeteredDimension.AGENT_RUNS, [1, 1, 1]) == 3

    def test_level_dimensions_take_the_maximum(self) -> None:
        # A workspace holding 5 GB all month used 5 GB, not 15. Summing
        # snapshots would multiply the storage bill by however often the
        # snapshot job happened to run — a configuration detail the
        # customer never agreed to be billed by.
        assert combine(MeteredDimension.VECTOR_STORAGE_MB, [5000, 5000, 5000]) == 5000

    def test_an_empty_period_is_zero_not_an_error(self) -> None:
        for dimension in MeteredDimension:
            assert combine(dimension, []) == 0

    def test_storage_dimensions_are_the_only_level_dimensions(self) -> None:
        assert {
            MeteredDimension.KNOWLEDGE_STORAGE_MB,
            MeteredDimension.VECTOR_STORAGE_MB,
        } == LEVEL_DIMENSIONS


class TestPeriodUsage:
    def _usage(self) -> PeriodUsage:
        return PeriodUsage(
            workspace_id="ws-1",
            period_start=_T0,
            period_end=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
            dimensions={
                MeteredDimension.AGENT_RUNS: DimensionUsage(
                    dimension=MeteredDimension.AGENT_RUNS,
                    quantity=1200,
                    cost_micro_usd=0,
                ),
                MeteredDimension.TOKENS: DimensionUsage(
                    dimension=MeteredDimension.TOKENS,
                    quantity=4_000_000,
                    cost_micro_usd=350_000,
                ),
            },
        )

    def test_a_dimension_with_no_events_reports_zero_not_missing(self) -> None:
        # Every dimension always has an answer; a null would make the
        # quota bar render nothing rather than empty.
        assert self._usage().quantity(MeteredDimension.MCP_CALLS) == 0
        assert self._usage().cost_micro_usd(MeteredDimension.MCP_CALLS) == 0

    def test_recorded_dimensions_report_their_totals(self) -> None:
        usage = self._usage()
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 1200
        assert usage.quantity(MeteredDimension.TOKENS) == 4_000_000

    def test_platform_cost_sums_across_dimensions(self) -> None:
        # Margin input, never an amount charged.
        assert self._usage().total_cost_micro_usd == 350_000

    def test_as_quantities_gives_the_shape_entitlement_lines_consume(self) -> None:
        quantities = self._usage().as_quantities()
        assert quantities[MeteredDimension.AGENT_RUNS] == 1200
        assert MeteredDimension.MCP_CALLS not in quantities
