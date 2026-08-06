"""Sliding-window-counter arithmetic. Pure — no Redis, no clock.

**Why this algorithm.** A fixed window lets a caller spend a full quota
at 11:59:59 and another at 12:00:00 — double the limit across one
second, which is exactly when a burst hurts. A true sliding window
(a sorted set of every request timestamp) fixes that but stores one
Redis entry per request, so the memory a workspace costs is proportional
to the traffic it sends — the wrong way round for a limiter that exists
to contain abusive traffic.

The counter approach keeps two integers per key and weights the previous
window by how much of it is still in view. It over-admits slightly at a
boundary when traffic is bursty and under-admits slightly when it is
even, and both errors are bounded by one window's worth. That is the
right trade for something on every request's hot path.

Everything here is a pure function of `(counts, elapsed, limit)` so the
decision can be tested without a clock or a server, and so the Redis
adapter contains nothing but two commands and a pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Whether this request proceeds, and what to tell the caller.

    `remaining` and `retry_after_seconds` are carried even when the
    request is allowed, because the response headers advertise them on
    every request — a client that only learns its budget by being
    refused cannot pace itself.
    """

    allowed: bool
    limit: int
    remaining: int
    #: Whole seconds until the window has moved enough to admit one more
    #: request. Always at least 1 when refused: `Retry-After: 0` invites
    #: an immediate retry, which is the behaviour the limit exists to
    #: prevent.
    retry_after_seconds: int
    #: Unix seconds at which the current window closes, for
    #: `RateLimit-Reset`.
    reset_at: int


def weighted_count(
    *,
    previous_window_count: int,
    current_window_count: int,
    elapsed_in_window: float,
    window_seconds: int,
) -> float:
    """Requests attributable to the last `window_seconds`.

    The previous window's count is weighted by the fraction of it still
    within view. At the very start of a window that is nearly all of it;
    by the end, nearly none.

    `elapsed_in_window` is clamped: a clock that jumps backwards would
    otherwise produce a weight above 1 and count the previous window
    more than once, refusing traffic that should pass.
    """
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    elapsed = min(max(elapsed_in_window, 0.0), float(window_seconds))
    overlap = (window_seconds - elapsed) / window_seconds
    return previous_window_count * overlap + current_window_count


def decide(
    *,
    limit: int | None,
    previous_window_count: int,
    current_window_count: int,
    elapsed_in_window: float,
    window_seconds: int,
    now_epoch: float,
) -> RateLimitDecision:
    """The whole decision, given what Redis returned.

    `limit=None` is unlimited — the same convention the billing plans use
    for every other quota, so "no limit configured" never has to mean
    zero. `limit=0` is a real limit that refuses everything, which is how
    a tier says "the API is not part of your plan".
    """
    reset_at = int(now_epoch + (window_seconds - min(elapsed_in_window, window_seconds)))

    if limit is None:
        # Advertised as the sentinel the RateLimit headers use for "no
        # ceiling" rather than as a large number a client might pace
        # itself against.
        return RateLimitDecision(
            allowed=True,
            limit=-1,
            remaining=-1,
            retry_after_seconds=0,
            reset_at=reset_at,
        )

    used = weighted_count(
        previous_window_count=previous_window_count,
        current_window_count=current_window_count,
        elapsed_in_window=elapsed_in_window,
        window_seconds=window_seconds,
    )
    # `used` already includes the request being decided: the counter is
    # incremented before this is called, so a limit of 1 admits exactly
    # one request rather than two.
    allowed = used <= limit
    remaining = max(int(limit - used), 0)

    return RateLimitDecision(
        allowed=allowed,
        limit=limit,
        remaining=remaining if allowed else 0,
        # Refused callers wait for the window to move, and never zero
        # seconds — `Retry-After: 0` invites the immediate retry this
        # exists to prevent.
        retry_after_seconds=0 if allowed else max(reset_at - int(now_epoch), 1),
        reset_at=reset_at,
    )


def window_start(*, now_epoch: float, window_seconds: int) -> int:
    """The epoch second the current window began.

    Derived from the clock rather than stored, so every replica agrees on
    which window a request falls in without coordinating.
    """
    return int(now_epoch // window_seconds) * window_seconds
