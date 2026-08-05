"""The dunning clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentverse_api.billing_service.domain.dunning import (
    DUNNING_SCHEDULE,
    DUNNING_WINDOW_DAYS,
    DunningAction,
    deadline,
    due_step,
    is_exhausted,
)

_FAILED_AT = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def _at(days: float) -> datetime:
    return _FAILED_AT + timedelta(days=days)


class TestSchedule:
    def test_the_schedule_matches_the_defined_cadence(self) -> None:
        # `saas-strategist` fixes the touchpoints at day 0/3/7/14. If a
        # later edit drops one, the emails silently stop matching the
        # documented recovery flow.
        assert [step.day for step in DUNNING_SCHEDULE] == [0, 3, 7, 14]

    def test_the_schedule_is_strictly_increasing(self) -> None:
        days = [step.day for step in DUNNING_SCHEDULE]
        assert days == sorted(set(days))

    def test_the_window_is_bounded_and_ends_in_cancellation(self) -> None:
        # `past_due` must be time-bounded — this is the assertion that
        # stops a subscription sitting unpaid forever.
        assert DUNNING_SCHEDULE[-1].action is DunningAction.CANCEL
        assert DUNNING_WINDOW_DAYS == 14


class TestDueStep:
    def test_the_first_touchpoint_fires_immediately(self) -> None:
        step = due_step(first_failure_at=_FAILED_AT, now=_FAILED_AT)
        assert step is not None
        assert step.day == 0
        assert step.action is DunningAction.NOTIFY

    def test_a_touchpoint_does_not_fire_early(self) -> None:
        # 2.9 days in is day 2. Retrying a few hours early would charge
        # the card before the bank's own retry window has passed, turning
        # one failure into two.
        step = due_step(first_failure_at=_FAILED_AT, now=_at(2.9))
        assert step is not None
        assert step.day == 0

    def test_the_retry_fires_once_its_day_arrives(self) -> None:
        step = due_step(first_failure_at=_FAILED_AT, now=_at(3))
        assert step is not None
        assert step.day == 3
        assert step.action is DunningAction.RETRY_PAYMENT

    def test_a_runner_that_was_down_does_not_replay_missed_touchpoints(self) -> None:
        # Returns the *furthest* due step, so resuming after a week of
        # downtime does not walk the customer through three days of
        # catch-up emails.
        step = due_step(first_failure_at=_FAILED_AT, now=_at(9))
        assert step is not None
        assert step.day == 7

    def test_past_the_window_the_answer_is_cancel(self) -> None:
        step = due_step(first_failure_at=_FAILED_AT, now=_at(20))
        assert step is not None
        assert step.action is DunningAction.CANCEL

    def test_a_clock_that_runs_backwards_does_not_fire_early(self) -> None:
        # Clock skew between the API and a worker is real; treating a
        # negative elapsed time as day 0 is the safe reading.
        step = due_step(first_failure_at=_FAILED_AT, now=_at(-5))
        assert step is not None
        assert step.day == 0


class TestExhaustion:
    def test_not_exhausted_inside_the_window(self) -> None:
        assert is_exhausted(first_failure_at=_FAILED_AT, now=_at(13.9)) is False

    def test_exhausted_exactly_on_the_deadline(self) -> None:
        assert is_exhausted(first_failure_at=_FAILED_AT, now=_at(14)) is True

    def test_deadline_is_the_window_after_the_first_failure(self) -> None:
        # The date shown to the customer. It is derived from the first
        # failure, so a repeatedly-failing card cannot push it out.
        assert deadline(_FAILED_AT) == _at(14)
