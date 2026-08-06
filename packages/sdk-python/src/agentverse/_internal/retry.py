"""When to retry, and how long to wait. Pure — no clock, no network.

Separated from the transport so the policy is testable without sleeping
and without a server, which is the only way to check the parts that
matter: that a `Retry-After` from the server wins over the client's own
guess, and that a non-idempotent request is not silently replayed.

**The rule that is easy to get wrong.** Retrying a `POST` that already
reached the server is how one agent run becomes two — and, since runs
cost money, how one charge becomes two. The API accepts an
`Idempotency-Key` on exactly the endpoints where that matters, so the
policy here is: retry a mutation only when the caller supplied a key, or
when the request provably never arrived (a connection error before any
response). Everything else retries freely, because it is a read.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

#: Retried because the request either did not arrive or the server said
#: "not now". A 500 is deliberately included: the API's own 5xx handler
#: fires before any business logic commits, so a retried request has not
#: half-happened.
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

#: Methods with no side effects. A retry of one of these cannot duplicate
#: anything, so it never needs an idempotency key.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DEFAULT_MAX_RETRIES = 2
_BASE_DELAY_SECONDS = 0.5
_MAX_DELAY_SECONDS = 30.0


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_seconds: float
    reason: str


def _backoff(attempt: int, jitter: random.Random | None = None) -> float:
    """Exponential with full jitter, capped.

    Full jitter rather than a fixed fraction: when a server recovers,
    every client that failed during the outage retries at once, and the
    thundering herd is what keeps it down. Randomising the *whole*
    interval spreads them properly — a ±20% band around a common base
    does not.
    """
    ceiling = min(_BASE_DELAY_SECONDS * (2**attempt), _MAX_DELAY_SECONDS)
    source = jitter or random
    return source.uniform(0.0, ceiling)


def decide(
    *,
    method: str,
    attempt: int,
    max_retries: int,
    status_code: int | None,
    retry_after: float | None = None,
    has_idempotency_key: bool = False,
    connection_failed: bool = False,
    jitter: random.Random | None = None,
) -> RetryDecision:
    """Whether to try again, and after how long.

    `attempt` is 0-based: the number of retries already made.
    `status_code=None` with `connection_failed=True` means no response
    was received at all.
    """
    if attempt >= max_retries:
        return RetryDecision(False, 0.0, "retry budget exhausted")

    is_safe = method.upper() in SAFE_METHODS

    if connection_failed:
        # No response was received, so nothing can have been applied
        # twice — except that "no response" does not prove "never
        # arrived": a reply lost on the way back looks identical. A safe
        # method is fine either way; a mutation needs the key.
        if is_safe or has_idempotency_key:
            return RetryDecision(True, _backoff(attempt, jitter), "connection failed")
        return RetryDecision(
            False,
            0.0,
            "connection failed on a mutation with no Idempotency-Key — retrying could "
            "duplicate it",
        )

    if status_code is None or status_code not in RETRYABLE_STATUSES:
        return RetryDecision(False, 0.0, "not a retryable status")

    # A 429 or 503 was refused before anything happened, so retrying is
    # safe even unkeyed — but a 500 or 502 does not say that, and the SDK
    # does not get to guess which one this deployment meant.
    if not is_safe and not has_idempotency_key and status_code not in (429, 503):
        return RetryDecision(
            False,
            0.0,
            "server error on a mutation with no Idempotency-Key — retrying could duplicate it",
        )

    if retry_after is not None:
        # The server's number always wins. It knows when the window
        # actually reopens; the client is guessing, and a client that
        # guesses shorter simply gets refused again.
        return RetryDecision(True, max(retry_after, 0.0), "server asked us to wait")

    return RetryDecision(True, _backoff(attempt, jitter), f"retryable status {status_code}")


def parse_retry_after(value: str | None) -> float | None:
    """`Retry-After` as seconds, or `None` if unusable.

    Only the delta-seconds form is handled; the HTTP-date form is
    accepted by the RFC but this API never sends it, and parsing dates
    from a header would mean trusting the client's clock to agree with
    the server's. `None` falls back to the SDK's own backoff, which is
    the safe direction.
    """
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None
