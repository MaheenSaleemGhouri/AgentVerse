"""Exercises docs/roadmap.md Phase 3's third acceptance criterion:
"given two identical job submissions within the lock's TTL window, only
one executes" — plus the safe-release property that makes a naive
`GET`-then-`DEL` release unsafe (CLAUDE.md Rule 20 concurrency care).
"""

from __future__ import annotations

import asyncio

from fakeredis.aioredis import FakeRedis

from agentverse_shared.locks.distributed_lock import DistributedLock, LockAcquisitionError

KEY = "lock:job:abc123"


async def test_second_concurrent_acquire_fails_while_first_holds_lock(
    fake_redis: FakeRedis,
) -> None:
    lock_a = DistributedLock(fake_redis, KEY, ttl_ms=30_000)
    lock_b = DistributedLock(fake_redis, KEY, ttl_ms=30_000)

    assert await lock_a.acquire() is True
    assert await lock_b.acquire() is False


async def test_lock_can_be_acquired_again_after_release(fake_redis: FakeRedis) -> None:
    lock_a = DistributedLock(fake_redis, KEY, ttl_ms=30_000)
    lock_b = DistributedLock(fake_redis, KEY, ttl_ms=30_000)

    await lock_a.acquire()
    await lock_a.release()

    assert await lock_b.acquire() is True


async def test_release_only_removes_the_key_if_still_owned_by_this_token(
    fake_redis: FakeRedis,
) -> None:
    """If this lock's TTL already expired and someone else acquired the
    same key, calling release() must not delete the new holder's lock.
    """
    lock_a = DistributedLock(fake_redis, KEY, ttl_ms=30_000)
    await lock_a.acquire()

    # Simulate lock_a's TTL expiring, then a different holder acquiring it.
    await fake_redis.delete(KEY)
    lock_b = DistributedLock(fake_redis, KEY, ttl_ms=30_000)
    await lock_b.acquire()

    await lock_a.release()  # stale token — must be a no-op against lock_b's key

    assert await fake_redis.get(KEY) is not None


async def test_release_with_no_prior_acquire_is_a_noop(fake_redis: FakeRedis) -> None:
    lock = DistributedLock(fake_redis, KEY)
    await lock.release()  # must not raise, must not touch the key
    assert await fake_redis.get(KEY) is None


async def test_context_manager_raises_when_already_locked(fake_redis: FakeRedis) -> None:
    async with DistributedLock(fake_redis, KEY):
        try:
            async with DistributedLock(fake_redis, KEY):
                raise AssertionError("second lock should not have been acquired")
        except LockAcquisitionError:
            pass


async def test_context_manager_releases_on_exit(fake_redis: FakeRedis) -> None:
    async with DistributedLock(fake_redis, KEY):
        assert await fake_redis.get(KEY) is not None

    assert await fake_redis.get(KEY) is None


async def test_only_one_of_two_racing_acquires_wins(fake_redis: FakeRedis) -> None:
    """A closer approximation of the acceptance criterion's "two
    identical submissions" scenario: both attempt acquisition
    concurrently via asyncio.gather; exactly one must win.
    """
    lock_a = DistributedLock(fake_redis, KEY)
    lock_b = DistributedLock(fake_redis, KEY)

    results = await asyncio.gather(lock_a.acquire(), lock_b.acquire())

    assert sorted(results) == [False, True]
