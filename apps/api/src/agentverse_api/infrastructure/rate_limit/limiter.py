"""The Redis half of the rate limiter.

Two integers per key, incremented in one pipeline, interpreted by the
pure functions in `window.py`. Nothing decides anything here — this file
exists to make the round trip cheap and to be the single place that
knows what happens when Redis is unreachable.

**Keys are namespaced per environment and per tenant**, following §8's
scheme: `{env}:api:ratelimit:{scope}:{identifier}:{window_start}`. Every
key carries a TTL of two windows, so an idle workspace leaves nothing
behind and the memory the limiter costs is proportional to *active*
callers rather than to registered ones.

**Failing closed is deliberate and has a cost.** §7 requires the limiter
to fail closed when Redis is unavailable, and it does: a request whose
budget cannot be checked is refused. The consequence is real and worth
stating plainly rather than discovering during an incident — a Redis
outage takes the authenticated API down rather than degrading it. That
is the trade the constitution makes, on the reasoning that an
unmetered API during an outage is how one workspace's runaway loop
becomes everyone's outage. `/health` and `/ready` are not rate limited,
so a failing limiter is still diagnosable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from agentverse_api.infrastructure.rate_limit.window import (
    RateLimitDecision,
    decide,
    window_start,
)

logger = logging.getLogger(__name__)

#: One minute. Short enough that a refused caller is not locked out for
#: long, long enough that the two-integer approximation is stable.
WINDOW_SECONDS = 60


class RateLimiterUnavailableError(Exception):
    """Redis could not answer, so no budget could be checked.

    Distinct from "over the limit": the caller did nothing wrong, and
    the route turns this into a 503 rather than a 429 so the difference
    is visible in their logs as well as ours.
    """


@dataclass(frozen=True, slots=True)
class RateLimitScope:
    """What is being limited, and to what.

    `identifier` is always resolved from the authenticated context —
    never from a path parameter or a header (Rule 6). A caller who could
    choose their own bucket could choose an empty one.
    """

    kind: str
    identifier: str
    limit: int | None


class RedisRateLimiter:
    def __init__(self, redis: Redis, *, environment: str, window_seconds: int = WINDOW_SECONDS):
        self._redis = redis
        self._environment = environment
        self._window = window_seconds

    def _key(self, scope: RateLimitScope, bucket: int) -> str:
        return f"{self._environment}:api:ratelimit:{scope.kind}:{scope.identifier}:{bucket}"

    async def check(self, scope: RateLimitScope) -> RateLimitDecision:
        """Count this request and decide whether it proceeds.

        The increment happens *before* the decision, so a refused request
        still counts against the window. That is intentional: a client
        hammering a limit should not be able to keep its own counter low
        by being refused, or the backoff never takes effect.
        """
        now = time.time()
        current_bucket = window_start(now_epoch=now, window_seconds=self._window)
        previous_bucket = current_bucket - self._window

        try:
            pipeline = self._redis.pipeline(transaction=False)
            pipeline.incr(self._key(scope, current_bucket))
            # Two windows, so the previous bucket is still readable for
            # the whole of the current one and no longer.
            pipeline.expire(self._key(scope, current_bucket), self._window * 2)
            pipeline.get(self._key(scope, previous_bucket))
            current_raw, _, previous_raw = await pipeline.execute()
        except RedisError as exc:
            # Logged rather than swallowed: this is the failure mode that
            # takes the API down, so it must be visible before the pages
            # start.
            logger.error(
                "rate_limiter_unavailable",
                extra={"scope_kind": scope.kind, "error": str(exc)},
            )
            raise RateLimiterUnavailableError(str(exc)) from exc

        return decide(
            limit=scope.limit,
            previous_window_count=int(previous_raw or 0),
            current_window_count=int(current_raw or 0),
            elapsed_in_window=now - current_bucket,
            window_seconds=self._window,
            now_epoch=now,
        )
