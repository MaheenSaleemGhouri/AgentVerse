"""Trivial job handler proving the queue infrastructure end-to-end
(docs/roadmap.md Phase 3) — no agent/run concept involved yet. A
payload with `force_fail: true` always fails, so the retry and DLQ
paths can be exercised on demand via the internal test endpoint.
"""

from __future__ import annotations

from agentverse_worker.queue.models import Job, JobResult


async def handle_echo_job(job: Job) -> JobResult:
    if job.payload.get("force_fail"):
        return JobResult.fail("forced failure requested via payload.force_fail")
    return JobResult.ok({"echoed": job.payload})
