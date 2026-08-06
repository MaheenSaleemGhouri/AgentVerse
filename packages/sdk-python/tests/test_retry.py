"""When the SDK retries, and — more importantly — when it refuses to.

The rule that carries real money: retrying a POST that already reached
the server is how one agent run becomes two, and how one charge becomes
two. Everything here is pure, so it runs without a clock or a server.
"""

from __future__ import annotations

import random

import pytest

from agentverse._internal.retry import (
    RETRYABLE_STATUSES,
    SAFE_METHODS,
    RetryDecision,
    decide,
    parse_retry_after,
)


def _decide(
    *,
    method: str = "GET",
    attempt: int = 0,
    max_retries: int = 2,
    status_code: int | None = 500,
    retry_after: float | None = None,
    has_idempotency_key: bool = False,
    connection_failed: bool = False,
) -> RetryDecision:
    """Typed wrapper so the assertions below stay type-checked.

    A `**kwargs: object` helper reads shorter and gives every assertion
    an `object` to poke at, which is how a renamed field slips past both
    mypy and the reader.
    """
    return decide(
        method=method,
        attempt=attempt,
        max_retries=max_retries,
        status_code=status_code,
        retry_after=retry_after,
        has_idempotency_key=has_idempotency_key,
        connection_failed=connection_failed,
        jitter=random.Random(0),
    )


class TestSafeMethods:
    @pytest.mark.parametrize("status", sorted(RETRYABLE_STATUSES))
    def test_a_read_retries_on_every_retryable_status(self, status: int) -> None:
        assert _decide(status_code=status).retry is True

    def test_a_read_does_not_retry_on_a_client_error(self) -> None:
        # 404 will be 404 again in a second. Retrying is noise for both
        # sides and delays the caller's real error.
        assert _decide(status_code=404).retry is False

    def test_a_read_retries_a_connection_failure(self) -> None:
        assert _decide(status_code=None, connection_failed=True).retry is True

    def test_the_safe_set_is_what_it_claims(self) -> None:
        assert frozenset({"GET", "HEAD", "OPTIONS"}) == SAFE_METHODS


class TestMutationsWithoutAKey:
    def test_a_post_does_not_retry_a_connection_failure(self) -> None:
        # "No response" does not prove "never arrived" — a reply lost on
        # the way back looks identical from here. Retrying could start a
        # second run and bill it.
        decision = _decide(method="POST", status_code=None, connection_failed=True)
        assert decision.retry is False
        assert "duplicate" in decision.reason

    def test_a_post_does_not_retry_a_500(self) -> None:
        # A 500 does not tell us whether anything committed first.
        decision = _decide(method="POST", status_code=500)
        assert decision.retry is False
        assert "duplicate" in decision.reason

    def test_a_post_does_retry_a_429(self) -> None:
        # A rate limit is refused *before* any work happens, so nothing
        # can have been applied — this one is safe without a key.
        assert _decide(method="POST", status_code=429, retry_after=1.0).retry is True

    def test_a_post_does_retry_a_503(self) -> None:
        # Same reasoning: the API returns 503 when it could not check the
        # budget, which is before it does anything.
        assert _decide(method="POST", status_code=503).retry is True


class TestMutationsWithAKey:
    def test_a_keyed_post_retries_a_connection_failure(self) -> None:
        # The key is exactly what makes a replay safe: the server returns
        # the original response instead of acting twice.
        assert (
            _decide(
                method="POST",
                status_code=None,
                connection_failed=True,
                has_idempotency_key=True,
            ).retry
            is True
        )

    def test_a_keyed_post_retries_a_500(self) -> None:
        assert _decide(method="POST", status_code=500, has_idempotency_key=True).retry is True

    def test_a_keyed_post_still_does_not_retry_a_422(self) -> None:
        # The request is wrong. A key does not make it right.
        assert _decide(method="POST", status_code=422, has_idempotency_key=True).retry is False


class TestBudget:
    def test_retries_stop_at_the_limit(self) -> None:
        assert _decide(attempt=2, max_retries=2).retry is False

    def test_zero_retries_means_none(self) -> None:
        assert _decide(attempt=0, max_retries=0).retry is False


class TestDelays:
    def test_the_servers_retry_after_wins(self) -> None:
        # The server knows when the window actually reopens. A client
        # that guesses shorter simply gets refused again.
        assert _decide(status_code=429, retry_after=7.5).delay_seconds == 7.5

    def test_backoff_grows_with_attempts(self) -> None:
        # Compared as ceilings rather than samples: the jitter is full,
        # so any single pair can invert.
        highest = [
            max(
                decide(
                    method="GET",
                    attempt=attempt,
                    max_retries=99,
                    status_code=500,
                    jitter=random.Random(seed),
                ).delay_seconds
                for seed in range(40)
            )
            for attempt in range(4)
        ]
        assert highest == sorted(highest)

    def test_the_delay_is_capped(self) -> None:
        assert (
            decide(
                method="GET",
                attempt=20,
                max_retries=99,
                status_code=500,
                jitter=random.Random(1),
            ).delay_seconds
            <= 30.0
        )

    def test_jitter_is_full_rather_than_a_narrow_band(self) -> None:
        # When a server recovers, every client that failed during the
        # outage retries at once. Randomising the whole interval spreads
        # them; a ±20% band around a common base does not.
        samples = {
            round(
                decide(
                    method="GET",
                    attempt=3,
                    max_retries=99,
                    status_code=500,
                    jitter=random.Random(seed),
                ).delay_seconds,
                3,
            )
            for seed in range(40)
        }
        assert min(samples) < 1.0
        assert max(samples) > 2.0

    def test_a_negative_retry_after_is_clamped(self) -> None:
        assert _decide(status_code=429, retry_after=-5.0).delay_seconds == 0.0


class TestRetryAfterParsing:
    def test_seconds_parse(self) -> None:
        assert parse_retry_after("12") == 12.0
        assert parse_retry_after(" 3.5 ") == 3.5

    def test_a_missing_header_is_none(self) -> None:
        assert parse_retry_after(None) is None

    def test_an_http_date_is_ignored_rather_than_guessed(self) -> None:
        # The RFC allows it and this API never sends it. Parsing dates
        # would mean trusting the client's clock to agree with the
        # server's; falling back to our own backoff is the safe
        # direction.
        assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None

    def test_a_negative_value_is_ignored(self) -> None:
        assert parse_retry_after("-1") is None
