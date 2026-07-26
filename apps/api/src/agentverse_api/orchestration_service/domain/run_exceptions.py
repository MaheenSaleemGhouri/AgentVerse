"""Domain-level errors for run submission. The interface layer
translates these to HTTP status codes (CLAUDE.md's shared error
envelope) — this layer never imports FastAPI/Starlette directly.
"""

from __future__ import annotations


class AgentNotRunnableError(Exception):
    """The agent doesn't exist for this workspace, or has no published
    version yet. Maps to 404 (no such agent, existence not leaked past
    workspace boundary) or 409 (exists but unpublished) at the interface
    layer depending on which condition applies.
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent {agent_id!r} is not runnable")


class RunSubmissionConflictError(Exception):
    """A concurrent request holding the idempotency lock never produced
    a run before the bounded poll gave up — extremely rare (would mean
    the lock holder crashed mid-request while still holding the lock).
    Maps to HTTP 409; the caller's own retry with the same
    Idempotency-Key is the correct recovery.
    """

    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(f"No run materialized for idempotency key {idempotency_key!r}")
