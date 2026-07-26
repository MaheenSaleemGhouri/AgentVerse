"""Redis-backed distributed lock (`SET NX PX` + a token-checked
optimistic-transaction release) preventing two duplicate submissions of
the same logical job from both executing — the exact primitive Phase
4's idempotent run-submission endpoint builds on (docs/roadmap.md
Phase 3).

The release is a `WATCH`/`MULTI`/`EXEC` transaction, not a plain
`GET`-then-`DEL`, because that pair isn't atomic: this lock's TTL could
expire and a different holder acquire the same key in the gap between
this process's `GET` and its `DEL`, which would then delete someone
else's lock. `WATCH`ing the key aborts the transaction (via
`WatchError`) if anyone else touched it between our read and our
delete, so we retry the whole check-and-delete instead of blindly
deleting a lock we no longer own. (A server-side Lua script would give
the same atomicity in one round trip, but requires scripting support
neither fakeredis's default build nor every managed Redis offering
provides — the transaction gets the same correctness without that
dependency.)
"""

from __future__ import annotations

import secrets
from types import TracebackType

from redis.asyncio import Redis
from redis.exceptions import WatchError

_MAX_RELEASE_RETRIES = 5


class LockAcquisitionError(Exception):
    """Raised by `async with DistributedLock(...)` when the lock is already held."""

    def __init__(self, key: str) -> None:
        super().__init__(f"could not acquire lock: {key}")
        self.key = key


class DistributedLock:
    def __init__(self, redis: Redis, key: str, *, ttl_ms: int = 30_000) -> None:
        self._redis = redis
        self._key = key
        self._ttl_ms = ttl_ms
        self._token: str | None = None

    async def acquire(self) -> bool:
        token = secrets.token_hex(16)
        acquired = await self._redis.set(self._key, token, nx=True, px=self._ttl_ms)
        if acquired:
            self._token = token
            return True
        return False

    async def release(self) -> None:
        """A no-op if this instance never held the lock (e.g. `acquire()`
        returned `False`) — releasing is only meaningful for a holder.
        """
        if self._token is None:
            return
        token = self._token
        for _attempt in range(_MAX_RELEASE_RETRIES):
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(self._key)
                    current = await pipe.get(self._key)
                    pipe.multi()  # type: ignore[no-untyped-call]  # redis-py's own stub is untyped here
                    if current == token:
                        pipe.delete(self._key)
                    await pipe.execute()
                break
            except WatchError:
                continue
        self._token = None

    async def __aenter__(self) -> DistributedLock:
        if not await self.acquire():
            raise LockAcquisitionError(self._key)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.release()
