"""Unit tests for the `team_session` job handler.

These cover what the handler owns rather than what the topologies own:
status transitions, idempotency against redelivery, the wall-clock
ceiling, and the guarantee that no failure path leaves a session stuck
in `running`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis

from agentverse_worker.jobs.team_session_job import handle_team_session_job
from agentverse_worker.queue.models import Job, JobResult, JobStatus
from agentverse_worker.teams import topologies
from agentverse_worker.teams.repository import TeamSessionRecord
from tests.teams.fakes import FakeRunner, FakeTeamRepository, make_member, make_team


@pytest.fixture(autouse=True)
def fake_runner(monkeypatch: pytest.MonkeyPatch) -> type[FakeRunner]:
    FakeRunner.reset()
    monkeypatch.setattr(topologies, "Runner", FakeRunner)
    return FakeRunner


@pytest.fixture
async def redis() -> Any:
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _job(payload: dict[str, Any]) -> Job:
    return Job(job_id="job-1", job_type="team_session", payload=payload, attempt=0, max_attempts=3)


def _succeeded(result: JobResult) -> bool:
    return result.status is JobStatus.SUCCEEDED


def _session(status: str = "queued") -> TeamSessionRecord:
    return TeamSessionRecord(
        id="session-1",
        workspace_id="ws-1",
        team_id="team-1",
        status=status,
        input={"prompt": "Summarise our Q3 pricing."},
    )


def _repo(**kwargs: Any) -> FakeTeamRepository:
    return FakeTeamRepository(
        session=kwargs.pop("session", _session()),
        team=kwargs.pop(
            "team",
            make_team(
                topology="sequential",
                members=[make_member(role="writer", position=0, name="writer")],
                **kwargs,
            ),
        ),
    )


async def _run(repo: FakeTeamRepository, redis: Any) -> JobResult:
    return await handle_team_session_job(
        _job({"session_id": "session-1"}),
        redis=redis,
        repo=repo,
        session_factory=None,  # type: ignore[arg-type]
    )


class TestHappyPath:
    async def test_marks_running_then_success(self, redis: Any) -> None:
        repo = _repo()
        result = await _run(repo, redis)
        assert _succeeded(result)
        assert [u["status"] for u in repo.status_updates] == ["running", "success"]

    async def test_records_output_cost_and_turns(self, redis: Any) -> None:
        repo = _repo()
        await _run(repo, redis)
        final = repo.status_updates[-1]
        assert final["output"] == "writer output"
        assert final["cost_micro_usd"] > 0
        assert final["total_turns"] >= 1

    async def test_emits_session_lifecycle_events(self, redis: Any) -> None:
        repo = _repo()
        await _run(repo, redis)
        assert repo.event_types()[0] == "session_started"
        assert repo.event_types()[-1] == "session_completed"


class TestIdempotency:
    @pytest.mark.parametrize("status", ["success", "error", "cancelled"])
    async def test_redelivery_of_a_terminal_session_does_not_re_execute(
        self, redis: Any, status: str
    ) -> None:
        """The queue is at-least-once. Without this check a redelivery
        would run the whole team a second time and bill for it
        (Rule 14)."""
        repo = _repo(session=_session(status=status))
        result = await _run(repo, redis)
        assert _succeeded(result)
        assert FakeRunner.calls == []
        assert repo.status_updates == []


class TestFailurePaths:
    async def test_missing_session_id_fails_without_touching_state(self, redis: Any) -> None:
        repo = _repo()
        result = await handle_team_session_job(
            _job({}),
            redis=redis,
            repo=repo,
            session_factory=None,  # type: ignore[arg-type]
        )
        assert not _succeeded(result)
        assert repo.status_updates == []

    async def test_unknown_session_fails(self, redis: Any) -> None:
        repo = FakeTeamRepository(session=None, team=None)
        result = await _run(repo, redis)
        assert not _succeeded(result)

    async def test_missing_team_marks_the_session_errored(self, redis: Any) -> None:
        """A session whose team vanished must not sit in `queued`
        forever — the runtime UI would render it as still waiting."""
        repo = FakeTeamRepository(session=_session(), team=None)
        result = await _run(repo, redis)
        assert not _succeeded(result)
        assert repo.status_updates[-1]["status"] == "error"

    async def test_topology_failure_becomes_an_errored_session_not_a_crash(
        self, redis: Any
    ) -> None:
        FakeRunner.raises = {"writer": RuntimeError("provider exploded")}
        repo = _repo()
        result = await _run(repo, redis)
        # `ok` so the queue does not retry: rerunning a team that failed
        # on its own logic would just spend the money again.
        assert _succeeded(result)
        assert repo.status_updates[-1]["status"] == "error"
        assert "provider exploded" in repo.status_updates[-1]["error_message"]
        assert "session_failed" in repo.event_types()

    async def test_cost_is_recorded_even_when_the_session_fails(self, redis: Any) -> None:
        """A session that aborted on its cost ceiling has, by definition,
        spent money. Writing null there would hide the very incident the
        ceiling exists to catch."""
        repo = _repo(max_cost_micro_usd=1)
        await _run(repo, redis)
        final = repo.status_updates[-1]
        assert final["status"] == "error"
        assert final["cost_micro_usd"] > 0

    async def test_wall_clock_ceiling_aborts_the_session(self, redis: Any) -> None:
        """A chain whose stages each finish inside their own timeout can
        still blow the team's budget several times over, so the ceiling
        wraps the whole topology rather than each stage."""
        repo = _repo(timeout_seconds=0)
        result = await _run(repo, redis)
        assert _succeeded(result)
        assert repo.status_updates[-1]["status"] == "error"
        assert "time budget" in repo.status_updates[-1]["error_message"]
