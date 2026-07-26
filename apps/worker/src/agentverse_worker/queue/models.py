"""Zero-framework job domain model (CLAUDE.md §5 clean architecture —
this module imports nothing from `redis` or `fastapi`; the queue
mechanics that move a `Job` in and out of Redis live in
`redis_stream_queue.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class JobStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Job:
    job_id: str
    job_type: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class JobResult:
    status: JobStatus
    output: dict[str, Any] | None = None
    error: str | None = None

    @classmethod
    def ok(cls, output: dict[str, Any] | None = None) -> JobResult:
        return cls(status=JobStatus.SUCCEEDED, output=output)

    @classmethod
    def fail(cls, error: str) -> JobResult:
        return cls(status=JobStatus.FAILED, error=error)


class JobHandler(Protocol):
    """A job handler is a pure async function from `Job` to `JobResult` —
    it never touches the queue/ack mechanics itself, so it's unit-testable
    with no Redis in the loop.
    """

    async def __call__(self, job: Job) -> JobResult: ...
