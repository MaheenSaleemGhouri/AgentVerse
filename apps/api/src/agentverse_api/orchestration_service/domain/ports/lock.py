"""Lock port (Protocol) — the application layer depends on this, never
directly on `agentverse_shared.locks.distributed_lock.DistributedLock`
or a raw Redis client (CLAUDE.md §5: infrastructure implements
domain-defined ports; a bare `Any`-typed Redis handle in `run_agent.py`
would leak an infrastructure concern past the domain boundary).
"""

from __future__ import annotations

from typing import Protocol


class Lock(Protocol):
    async def acquire(self) -> bool: ...
    async def release(self) -> None: ...
