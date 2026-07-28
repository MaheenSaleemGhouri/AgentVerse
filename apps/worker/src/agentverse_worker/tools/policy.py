"""Execution policy around a tool call: circuit breaker, result cache,
and retry backoff.

All three are Redis-backed and shared across the worker fleet, which is
the point. A per-process circuit breaker on a fleet of eight workers
means a dead MCP server gets hammered by eight independent breakers, each
having to fail on its own before it opens — the failure the breaker
exists to stop happens eight times over.

None of this is the system of record. Losing Redis re-closes every
breaker and empties every cache: calls get slower and a dead server is
retried again, but nothing becomes *incorrect* (Rule 13).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

#: Consecutive failures before the breaker opens. Low, because the thing
#: being protected is an agent run the user is watching — three failed
#: round trips is already a visibly stalled run.
DEFAULT_FAILURE_THRESHOLD = 3
#: How long an open breaker stays open before allowing one probe.
DEFAULT_OPEN_SECONDS = 60
#: Ceiling on retry backoff, so a policy with many retries cannot turn
#: into a long sleep inside a bounded run.
MAX_BACKOFF_SECONDS = 8.0


def _key(*parts: str) -> str:
    """Redis key naming per CLAUDE.md §8: `{env}:{service}:{domain}:...`.

    The env prefix is applied by the caller's client configuration; this
    builds the domain-scoped remainder.
    """
    return ":".join(("tools", *parts))


@dataclass(frozen=True, slots=True)
class BreakerState:
    is_open: bool
    failure_count: int
    #: Seconds until the breaker allows another attempt. Zero when closed.
    retry_after_seconds: int


class CircuitBreaker:
    """Per-server breaker, keyed by workspace and installed server.

    Keyed by *installation*, not by catalog entry: two workspaces
    installing the same GitHub server have different credentials and
    different network paths, and one workspace's expired token must not
    open the breaker for everybody.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        open_seconds: int = DEFAULT_OPEN_SECONDS,
    ) -> None:
        self._redis = redis
        self._threshold = failure_threshold
        self._open_seconds = open_seconds

    def _failure_key(self, workspace_id: str, server_id: str) -> str:
        return _key("breaker", workspace_id, server_id, "failures")

    def _open_key(self, workspace_id: str, server_id: str) -> str:
        return _key("breaker", workspace_id, server_id, "open")

    async def state(self, *, workspace_id: str, server_id: str) -> BreakerState:
        open_key = self._open_key(workspace_id, server_id)
        ttl = await self._redis.ttl(open_key)
        raw = await self._redis.get(self._failure_key(workspace_id, server_id))
        failures = int(raw) if raw else 0
        # `ttl` is -2 for a missing key and -1 for a key with no expiry.
        # Only a positive TTL means genuinely open.
        return BreakerState(
            is_open=ttl > 0, failure_count=failures, retry_after_seconds=max(0, ttl)
        )

    async def record_success(self, *, workspace_id: str, server_id: str) -> None:
        """Clears the breaker completely, not by decrementing.

        A server that just answered correctly is working; carrying a
        residual failure count would open the breaker on the next
        isolated blip.
        """
        await self._redis.delete(
            self._failure_key(workspace_id, server_id),
            self._open_key(workspace_id, server_id),
        )

    async def record_failure(self, *, workspace_id: str, server_id: str) -> BreakerState:
        failure_key = self._failure_key(workspace_id, server_id)
        failures = await self._redis.incr(failure_key)
        # Expire the counter so isolated failures spread over hours never
        # accumulate into an open breaker.
        await self._redis.expire(failure_key, self._open_seconds * 2)

        if failures >= self._threshold:
            await self._redis.set(
                self._open_key(workspace_id, server_id), "1", ex=self._open_seconds
            )
            return BreakerState(
                is_open=True, failure_count=int(failures), retry_after_seconds=self._open_seconds
            )
        return BreakerState(is_open=False, failure_count=int(failures), retry_after_seconds=0)


class ResultCache:
    """Caches identical tool calls for a grant-configured TTL.

    Only ever populated for calls the permission grant marks cacheable
    (`cache_ttl_seconds > 0`), and only for successful ones — caching an
    error would make a transient failure sticky for the whole TTL.

    The key includes the *arguments*, so `list_issues(repo="a")` and
    `list_issues(repo="b")` are different entries. It also includes the
    workspace: two tenants calling the same tool with the same arguments
    against their own credentials get different data, and a shared entry
    would be a cross-tenant leak (Rule 11).
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def fingerprint(arguments: dict[str, Any]) -> str:
        """Stable hash of the arguments.

        `sort_keys` matters: two dicts with the same content in a
        different insertion order are the same call, and without sorting
        they would miss each other's cache entries.
        """
        encoded = json.dumps(arguments, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()[:32]

    def _key(self, workspace_id: str, server_id: str, tool_name: str, fingerprint: str) -> str:
        return _key("cache", workspace_id, server_id, tool_name, fingerprint)

    async def get(
        self, *, workspace_id: str, server_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> str | None:
        value = await self._redis.get(
            self._key(workspace_id, server_id, tool_name, self.fingerprint(arguments))
        )
        return value if isinstance(value, str) else None

    async def put(
        self,
        *,
        workspace_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: str,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return
        await self._redis.set(
            self._key(workspace_id, server_id, tool_name, self.fingerprint(arguments)),
            result,
            ex=ttl_seconds,
        )


class CallBudget:
    """Per-run ceiling on how many times a grant's tools may be called.

    Bounds a tool loop: an agent that keeps calling the same tool is
    within its step limit and its cost limit right up until it is not,
    and a per-tool budget catches it earlier and more cheaply.

    Scoped to the run, so the counter disappears with the run rather than
    needing a sweep.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, run_id: str, server_id: str) -> str:
        return _key("budget", run_id, server_id)

    async def consume(self, *, run_id: str, server_id: str, limit: int, ttl_seconds: int) -> bool:
        """Increments and reports whether the call is within budget.

        Increment-then-check rather than check-then-increment: the latter
        is a race between concurrent tool calls in a parallel topology,
        and the race is in the permissive direction.
        """
        key = self._key(run_id, server_id)
        used = await self._redis.incr(key)
        if used == 1:
            await self._redis.expire(key, ttl_seconds)
        return int(used) <= limit


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff, capped.

    No jitter here deliberately: the caller is one agent run, not a
    thundering herd of clients recovering together, and the thing that
    stops a fleet from synchronising on a dead server is the circuit
    breaker, not jitter on this path.
    """
    return min(MAX_BACKOFF_SECONDS, 0.5 * float(2 ** max(0, attempt - 1)))
