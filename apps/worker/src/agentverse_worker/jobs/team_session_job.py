"""Executes a `team_session` job — the multi-agent analogue of
`agent_run_job`.

Structure deliberately mirrors the single-agent handler: resolve, mark
running, execute inside a bounded scope, translate every failure into a
recorded session status rather than a raw crash. A team session that
dies without updating its row would sit in `running` forever, which the
runtime UI would render as a team that is still working.

Idempotency (Rule 14): a redelivered job whose session is already
terminal returns success without re-executing. The queue guarantees
at-least-once delivery, so without this check a redelivery would run the
whole team a second time and bill for it.
"""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentverse_worker.queue.models import Job, JobResult
from agentverse_worker.teams.repository import TeamRepositoryProtocol
from agentverse_worker.teams.runtime import Bounds, TeamAbortedError, TeamRunContext
from agentverse_worker.teams.shared_memory import SharedMemoryStore
from agentverse_worker.teams.topologies import execute_topology

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"success", "error", "cancelled"})


async def handle_team_session_job(
    job: Job,
    *,
    redis: Redis,
    repo: TeamRepositoryProtocol,
    session_factory: async_sessionmaker[AsyncSession],
) -> JobResult:
    """Collaborators are injected rather than constructed here so the
    topology logic, bounds, and status transitions stay unit-testable
    against fakes without a live Postgres (CLAUDE.md §11).
    """
    session_id = job.payload.get("session_id")
    if not session_id:
        return JobResult.fail("team_session job payload missing session_id")

    session = await repo.get_session(session_id)
    if session is None:
        return JobResult.fail(f"team_session {session_id}: no such session")
    if session.status in _TERMINAL_STATUSES:
        logger.info(
            "team_session_already_terminal session=%s status=%s", session_id, session.status
        )
        return JobResult.ok({"session_id": session_id, "status": session.status})

    team = await repo.get_team(session.team_id, workspace_id=session.workspace_id)
    if team is None:
        await repo.update_session_status(
            session_id=session_id, status="error", error_message="team not found"
        )
        return JobResult.fail(f"team_session {session_id}: team {session.team_id} not found")

    await repo.update_session_status(session_id=session_id, status="running")

    ctx = TeamRunContext(
        repo=repo,
        redis=redis,
        session_id=session_id,
        workspace_id=session.workspace_id,
        bounds=Bounds(
            max_turns=team.max_turns,
            max_cost_micro_usd=team.max_cost_micro_usd,
            timeout_seconds=team.timeout_seconds,
        ),
    )
    memory = (
        SharedMemoryStore(
            session_factory=session_factory,
            workspace_id=session.workspace_id,
            team_id=team.id,
            team_session_id=session_id,
            sharing_enabled=team.shared_memory_enabled,
        )
        if session_factory is not None
        else None
    )

    await ctx.emit(
        "session_started",
        payload={
            "team_id": team.id,
            "team_name": team.name,
            "topology": team.topology,
            "member_count": len(team.members),
        },
    )

    try:
        # The wall-clock ceiling wraps the whole topology rather than
        # each stage: a four-stage chain each finishing just inside its
        # own timeout would still blow the team's budget several times
        # over (Rule 17 — all three bounds, and time is measured on the
        # thing the user actually waits for).
        async with asyncio.timeout(team.timeout_seconds):
            output = await execute_topology(
                team=team,
                prompt=str(session.input.get("prompt", "")),
                ctx=ctx,
                memory=memory,
                session_factory=session_factory,
            )
    except TimeoutError:
        reason = f"exceeded team time budget of {team.timeout_seconds}s"
        await _fail(repo, ctx, session_id=session_id, reason=reason)
        return JobResult.ok({"session_id": session_id, "status": "error"})
    except TeamAbortedError as exc:
        await _fail(repo, ctx, session_id=session_id, reason=exc.reason)
        return JobResult.ok({"session_id": session_id, "status": "error"})
    except Exception as exc:  # noqa: BLE001 - translated into a session failure
        logger.exception("team_session_job_failed session_id=%s", session_id)
        await _fail(repo, ctx, session_id=session_id, reason=str(exc))
        return JobResult.ok({"session_id": session_id, "status": "error"})

    await repo.update_session_status(
        session_id=session_id,
        status="success",
        output=output,
        cost_micro_usd=ctx.total_cost_micro_usd,
        total_turns=ctx.total_turns,
    )
    await ctx.emit(
        "session_completed",
        payload={"output": output, "total_turns": ctx.total_turns},
        cost_micro_usd=ctx.total_cost_micro_usd,
    )
    return JobResult.ok({"session_id": session_id, "status": "success"})


async def _fail(
    repo: TeamRepositoryProtocol,
    ctx: TeamRunContext,
    *,
    session_id: str,
    reason: str,
) -> None:
    """Cost and turns are recorded on failure too.

    A session that aborted on its cost ceiling has, by definition, spent
    money; writing null there would make the very incident the ceiling
    exists to catch invisible in the billing record.
    """
    await repo.update_session_status(
        session_id=session_id,
        status="error",
        error_message=reason,
        cost_micro_usd=ctx.total_cost_micro_usd,
        total_turns=ctx.total_turns,
    )
    await ctx.emit(
        "session_failed",
        payload={"reason": reason, "total_turns": ctx.total_turns},
        cost_micro_usd=ctx.total_cost_micro_usd,
    )
