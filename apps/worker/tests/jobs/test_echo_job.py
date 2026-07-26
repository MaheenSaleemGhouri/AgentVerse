from agentverse_worker.jobs.echo_job import handle_echo_job
from agentverse_worker.queue.models import Job, JobStatus


async def test_echo_job_returns_payload_on_success() -> None:
    job = Job(job_id="j1", job_type="echo", payload={"hello": "world"}, attempt=0, max_attempts=3)

    result = await handle_echo_job(job)

    assert result.status is JobStatus.SUCCEEDED
    assert result.output == {"echoed": {"hello": "world"}}


async def test_echo_job_fails_when_forced() -> None:
    job = Job(job_id="j2", job_type="echo", payload={"force_fail": True}, attempt=0, max_attempts=3)

    result = await handle_echo_job(job)

    assert result.status is JobStatus.FAILED
    assert result.error is not None
