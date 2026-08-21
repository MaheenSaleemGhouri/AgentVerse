"""Unit tests for `domain.eval_run.EvalRun`'s aggregation — pure."""

from __future__ import annotations

from datetime import UTC, datetime

from agentverse_api.orchestration_service.domain.eval_run import EvalRun, ExampleResult

_T0 = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _result(*, passed: bool, cost: int = 10, latency: int = 100) -> ExampleResult:
    return ExampleResult(
        golden_example_id="ex-1", passed=passed, reason="", cost_micro_usd=cost, latency_ms=latency
    )


class TestPassed:
    def test_passes_only_when_every_example_passed(self) -> None:
        run = EvalRun(
            id="run-1",
            prompt_version_id="v-1",
            started_at=_T0,
            completed_at=_T0,
            results=(_result(passed=True), _result(passed=True)),
        )
        assert run.passed is True

    def test_a_single_failing_example_fails_the_whole_run(self) -> None:
        # The acceptance criterion's "a prompt version fails its
        # golden-dataset eval" is singular, not a majority threshold.
        run = EvalRun(
            id="run-1",
            prompt_version_id="v-1",
            started_at=_T0,
            completed_at=_T0,
            results=(_result(passed=True), _result(passed=False)),
        )
        assert run.passed is False

    def test_zero_examples_never_counts_as_passed(self) -> None:
        run = EvalRun(id="run-1", prompt_version_id="v-1", started_at=_T0, completed_at=_T0)
        assert run.passed is False


class TestAggregates:
    def test_totals_sum_across_examples(self) -> None:
        run = EvalRun(
            id="run-1",
            prompt_version_id="v-1",
            started_at=_T0,
            completed_at=_T0,
            results=(
                _result(passed=True, cost=100, latency=50),
                _result(passed=False, cost=200, latency=75),
            ),
        )
        assert run.total_examples == 2
        assert run.passed_examples == 1
        assert run.total_cost_micro_usd == 300
        assert run.total_latency_ms == 125
