"""Sliding-window-counter arithmetic.

The decision is pure, so these run without Redis or a clock. What they
pin down is the behaviour at the boundary — which is the only place the
algorithm choice is visible, and the reason a plain fixed window was
rejected.
"""

from __future__ import annotations

import pytest

from agentverse_api.infrastructure.rate_limit.window import (
    decide,
    weighted_count,
    window_start,
)

_WINDOW = 60
_NOW = 1_800_000_000.0


def _decide(
    *,
    limit: int | None,
    previous: int = 0,
    current: int = 0,
    elapsed: float = 0.0,
) -> object:
    return decide(
        limit=limit,
        previous_window_count=previous,
        current_window_count=current,
        elapsed_in_window=elapsed,
        window_seconds=_WINDOW,
        now_epoch=_NOW,
    )


class TestWeighting:
    def test_the_previous_window_counts_fully_at_the_start(self) -> None:
        # At the instant a window opens, essentially all of the previous
        # one is still within view — which is exactly what stops a caller
        # spending a full quota either side of the boundary.
        assert weighted_count(
            previous_window_count=100,
            current_window_count=0,
            elapsed_in_window=0.0,
            window_seconds=_WINDOW,
        ) == pytest.approx(100.0)

    def test_the_previous_window_has_faded_by_the_end(self) -> None:
        assert weighted_count(
            previous_window_count=100,
            current_window_count=0,
            elapsed_in_window=float(_WINDOW),
            window_seconds=_WINDOW,
        ) == pytest.approx(0.0)

    def test_halfway_through_it_counts_half(self) -> None:
        assert weighted_count(
            previous_window_count=100,
            current_window_count=10,
            elapsed_in_window=30.0,
            window_seconds=_WINDOW,
        ) == pytest.approx(60.0)

    def test_a_backwards_clock_cannot_double_count(self) -> None:
        # Negative elapsed would otherwise produce a weight above 1 and
        # refuse traffic that should pass — a limiter that gets stricter
        # when NTP steps backwards.
        assert weighted_count(
            previous_window_count=100,
            current_window_count=0,
            elapsed_in_window=-30.0,
            window_seconds=_WINDOW,
        ) == pytest.approx(100.0)

    def test_a_forwards_clock_cannot_produce_a_negative_weight(self) -> None:
        assert weighted_count(
            previous_window_count=100,
            current_window_count=5,
            elapsed_in_window=1_000.0,
            window_seconds=_WINDOW,
        ) == pytest.approx(5.0)

    def test_a_zero_window_is_refused_rather_than_dividing_by_zero(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            weighted_count(
                previous_window_count=0,
                current_window_count=0,
                elapsed_in_window=0.0,
                window_seconds=0,
            )


class TestDecision:
    def test_a_request_within_the_limit_is_allowed(self) -> None:
        decision = _decide(limit=100, current=1)
        assert decision.allowed is True
        assert decision.remaining == 99

    def test_the_request_being_decided_is_already_counted(self) -> None:
        # The counter is incremented before the decision, so a limit of 1
        # admits exactly one request. Off by one here means every limit
        # is really limit+1.
        assert _decide(limit=1, current=1).allowed is True
        assert _decide(limit=1, current=2).allowed is False

    def test_exceeding_the_limit_refuses(self) -> None:
        decision = _decide(limit=10, current=11)
        assert decision.allowed is False
        assert decision.remaining == 0

    def test_the_boundary_burst_is_caught(self) -> None:
        # The whole reason for the weighting. A caller that spent its
        # entire quota in the previous window has almost none left one
        # second into the new one — where a fixed window would have reset
        # and handed it another hundred.
        decision = _decide(limit=100, previous=100, current=1, elapsed=1.0)
        assert decision.remaining == 0
        assert _decide(limit=100, previous=100, current=2, elapsed=1.0).allowed is False

    def test_a_fixed_window_would_have_allowed_that_burst(self) -> None:
        # The contrast, stated: with the previous window ignored, the
        # same caller is one request into a fresh hundred.
        assert _decide(limit=100, previous=0, current=2, elapsed=1.0).remaining == 98

    def test_the_same_burst_passes_once_the_window_has_moved_on(self) -> None:
        decision = _decide(limit=100, previous=100, current=1, elapsed=59.0)
        assert decision.allowed is True

    def test_a_refusal_never_says_retry_immediately(self) -> None:
        # `Retry-After: 0` invites the immediate retry the limit exists
        # to prevent.
        decision = _decide(limit=1, current=99, elapsed=59.9)
        assert decision.allowed is False
        assert decision.retry_after_seconds >= 1

    def test_an_allowed_request_asks_for_no_wait(self) -> None:
        assert _decide(limit=100, current=1).retry_after_seconds == 0

    def test_remaining_never_goes_negative(self) -> None:
        assert _decide(limit=10, current=1_000).remaining == 0


class TestUnlimited:
    def test_none_means_unlimited(self) -> None:
        # `None` is the same convention every other quota uses, so "not
        # configured" never silently means zero.
        decision = _decide(limit=None, current=1_000_000)
        assert decision.allowed is True

    def test_unlimited_advertises_the_sentinel_not_a_large_number(self) -> None:
        # A client shown a large number would pace itself against it.
        decision = _decide(limit=None)
        assert decision.limit == -1
        assert decision.remaining == -1

    def test_a_limit_of_zero_refuses_everything(self) -> None:
        # Distinct from unlimited: this is how a tier says "the API is
        # not part of your plan" as a number.
        assert _decide(limit=0, current=1).allowed is False


class TestWindowStart:
    def test_the_window_is_derived_from_the_clock(self) -> None:
        # Derived rather than stored, so every replica agrees on which
        # window a request falls in without coordinating.
        assert window_start(now_epoch=1_800_000_037.5, window_seconds=60) == 1_800_000_000

    def test_an_exact_boundary_belongs_to_the_new_window(self) -> None:
        assert window_start(now_epoch=1_800_000_060.0, window_seconds=60) == 1_800_000_060

    def test_two_moments_in_one_window_share_a_start(self) -> None:
        assert window_start(now_epoch=_NOW + 1, window_seconds=60) == window_start(
            now_epoch=_NOW + 59, window_seconds=60
        )
