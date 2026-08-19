"""`/api/v1/workspaces/{workspace_id}/teams` — AI team CRUD, membership,
execution, and runtime reads.

Naming note, because two things in the product are called "team":
`/workspaces/{id}/team` is workspace membership (humans, RBAC) and lives
in the auth service; this is `/teams`, plural, and is teams of *agents*.
They share no table, route, or repository (ADR-0009).

`workspace_id` is never read from the path parameter — it comes from the
authenticated `WorkspaceContext` the role dependency resolves (Rule 6).
The path segment exists for URL shape and is validated by that same
dependency.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_member,
    require_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import get_audit_service
from agentverse_api.orchestration_service.application.execute_team import (
    LockFactory,
    TeamNotRunnableError,
    execute_team,
)
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.team_repository import TeamRepository
from agentverse_api.orchestration_service.domain.run_exceptions import RunSubmissionConflictError
from agentverse_api.orchestration_service.domain.team_entities import (
    Team,
    TeamMember,
    TeamMemberRole,
    TeamSession,
    TeamTopology,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_agent_repository,
    get_job_queue_producer,
    get_lock_factory,
    get_team_repository,
)
from agentverse_api.orchestration_service.interface.schemas.teams import (
    AddMemberRequest,
    CommunicationResponse,
    CreateTeamRequest,
    ExecuteTeamRequest,
    ExecutionEventResponse,
    HandoffResponse,
    ReorderMembersRequest,
    TeamAnalyticsResponse,
    TeamMemberResponse,
    TeamResponse,
    TeamSessionPage,
    TeamSessionResponse,
    UpdateTeamRequest,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/teams", tags=["teams"])

#: Page size for runtime reads. Bounded server-side as well as by the
#: query parameter so a client cannot ask for an unbounded page of a
#: partitioned trace table.
MAX_PAGE_SIZE = 200


def _member_response(member: TeamMember) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=member.id,
        team_id=member.team_id,
        agent_id=member.agent_id,
        role=member.role.value,
        position=member.position,
        handoff_description=member.handoff_description,
        can_receive_handoff=member.can_receive_handoff,
        created_at=member.created_at,
    )


def _team_response(team: Team) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        workspace_id=team.workspace_id,
        name=team.name,
        description=team.description,
        topology=team.topology.value,
        objective=team.objective,
        max_turns=team.max_turns,
        max_cost_micro_usd=team.max_cost_micro_usd,
        timeout_seconds=team.timeout_seconds,
        shared_memory_enabled=team.shared_memory_enabled,
        shared_knowledge_base_ids=team.shared_knowledge_base_ids,
        created_at=team.created_at,
        updated_at=team.updated_at,
        members=[_member_response(m) for m in team.ordered_members()],
    )


def _session_response(session: TeamSession) -> TeamSessionResponse:
    return TeamSessionResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        team_id=session.team_id,
        status=session.status.value,
        input=session.input,
        output=session.output,
        error_message=session.error_message,
        cost_micro_usd=session.cost_micro_usd,
        total_turns=session.total_turns,
        started_at=session.started_at,
        completed_at=session.completed_at,
        created_at=session.created_at,
    )


async def _require_team(repo: TeamRepository, context: WorkspaceContext, team_id: str) -> Team:
    """404 for a team in another workspace, not 403.

    A 403 would confirm the team exists, which leaks the existence of
    another tenant's resources (CLAUDE.md §10).
    """
    team = await repo.get_team(workspace_id=context.workspace_id, team_id=team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


async def _require_session(
    repo: TeamRepository, context: WorkspaceContext, session_id: str
) -> TeamSession:
    session = await repo.get_session(workspace_id=context.workspace_id, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team session not found")
    return session


# --- teams ---------------------------------------------------------------


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team_route(
    body: CreateTeamRequest,
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
    audit: AuditService = Depends(get_audit_service),
) -> TeamResponse:
    team = await repo.create_team(
        workspace_id=context.workspace_id,
        name=body.name,
        description=body.description,
        topology=TeamTopology(body.topology),
        objective=body.objective,
        max_turns=body.max_turns,
        max_cost_micro_usd=body.max_cost_micro_usd,
        timeout_seconds=body.timeout_seconds,
        shared_memory_enabled=body.shared_memory_enabled,
        shared_knowledge_base_ids=body.shared_knowledge_base_ids,
        created_by_user_id=context.user_id,
    )
    await audit.record(
        action="team.created",
        outcome="success",
        workspace_id=context.workspace_id,
        actor_user_id=context.user_id,
        target=team.id,
    )
    return _team_response(team)


@router.get("", response_model=list[TeamResponse])
async def list_teams_route(
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> list[TeamResponse]:
    return [_team_response(t) for t in await repo.list_teams(workspace_id=context.workspace_id)]


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team_route(
    team_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> TeamResponse:
    return _team_response(await _require_team(repo, context, team_id))


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team_route(
    team_id: str,
    body: UpdateTeamRequest,
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
    audit: AuditService = Depends(get_audit_service),
) -> TeamResponse:
    await _require_team(repo, context, team_id)
    # `exclude_unset` rather than `exclude_none`: clearing `objective` by
    # sending null is a legitimate edit, and excluding None would make it
    # silently impossible.
    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    if "topology" in changes and changes["topology"] is not None:
        changes["topology"] = TeamTopology(changes["topology"])
    updated = await repo.update_team(
        workspace_id=context.workspace_id, team_id=team_id, changes=changes
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    await audit.record(
        action="team.updated",
        outcome="success",
        workspace_id=context.workspace_id,
        actor_user_id=context.user_id,
        target=team_id,
    )
    return _team_response(updated)


@router.post("/{team_id}/duplicate", response_model=TeamResponse, status_code=201)
async def duplicate_team_route(
    team_id: str,
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
) -> TeamResponse:
    """Copies a team's configuration and seats, not its history.

    Sessions, handoffs, and memory belong to the original run and would
    be false if attributed to a new team. Members are copied as seats
    pointing at the same agents — the agents themselves are never
    duplicated, since a team composes agents rather than owning them.
    """
    original = await _require_team(repo, context, team_id)
    copy = await repo.create_team(
        workspace_id=context.workspace_id,
        name=f"{original.name} (copy)",
        description=original.description,
        topology=original.topology,
        objective=original.objective,
        max_turns=original.max_turns,
        max_cost_micro_usd=original.max_cost_micro_usd,
        timeout_seconds=original.timeout_seconds,
        shared_memory_enabled=original.shared_memory_enabled,
        shared_knowledge_base_ids=list(original.shared_knowledge_base_ids),
        created_by_user_id=context.user_id,
    )
    for member in original.ordered_members():
        await repo.add_member(
            workspace_id=context.workspace_id,
            team_id=copy.id,
            agent_id=member.agent_id,
            role=member.role,
            position=member.position,
            handoff_description=member.handoff_description,
            can_receive_handoff=member.can_receive_handoff,
        )
    return _team_response(await _require_team(repo, context, copy.id))


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_team_route(
    team_id: str,
    context: WorkspaceContext = Depends(require_admin),
    repo: TeamRepository = Depends(get_team_repository),
) -> None:
    """Admin-only and soft — a team's session history has to stay
    resolvable so completed runs still render after the team is gone.
    """
    if not await repo.soft_delete_team(workspace_id=context.workspace_id, team_id=team_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")


# --- members -------------------------------------------------------------


@router.post(
    "/{team_id}/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED
)
async def add_member_route(
    team_id: str,
    body: AddMemberRequest,
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> TeamMemberResponse:
    team = await _require_team(repo, context, team_id)
    agent = await agent_repo.get_agent(workspace_id=context.workspace_id, agent_id=body.agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if any(m.agent_id == body.agent_id for m in team.members):
        # Mirrors the DB's `uq_team_member_agent` constraint with a
        # readable message rather than letting an IntegrityError surface
        # as a 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That agent is already a member of this team.",
        )
    member = await repo.add_member(
        workspace_id=context.workspace_id,
        team_id=team_id,
        agent_id=body.agent_id,
        role=TeamMemberRole(body.role),
        position=body.position,
        handoff_description=body.handoff_description,
        can_receive_handoff=body.can_receive_handoff,
    )
    return _member_response(member)


@router.delete(
    "/{team_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_member_route(
    team_id: str,
    member_id: str,
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
) -> None:
    await _require_team(repo, context, team_id)
    if not await repo.remove_member(
        workspace_id=context.workspace_id, team_id=team_id, member_id=member_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")


@router.put("/{team_id}/members/order", response_model=TeamResponse)
async def reorder_members_route(
    team_id: str,
    body: ReorderMembersRequest,
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
) -> TeamResponse:
    """Drag-and-drop ordering.

    The submitted list must name exactly the team's current members: a
    partial list would leave the omitted ones at stale positions, which
    for a `sequential` team silently changes what runs when.
    """
    team = await _require_team(repo, context, team_id)
    submitted = set(body.member_ids)
    actual = {m.id for m in team.members}
    if submitted != actual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="member_ids must list exactly the team's current members, in the new order.",
        )
    await repo.reorder_members(
        workspace_id=context.workspace_id, team_id=team_id, member_ids_in_order=body.member_ids
    )
    return _team_response(await _require_team(repo, context, team_id))


# --- execution -----------------------------------------------------------


@router.post(
    "/{team_id}/sessions",
    response_model=TeamSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def execute_team_route(
    team_id: str,
    body: ExecuteTeamRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: WorkspaceContext = Depends(require_member),
    repo: TeamRepository = Depends(get_team_repository),
    agent_repo: AgentRepository = Depends(get_agent_repository),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
    lock_factory: LockFactory = Depends(get_lock_factory),
) -> TeamSessionResponse:
    """`202 Accepted` with a session id — execution is a worker job, never
    inline in the request (Rule 14).
    """
    try:
        session = await execute_team(
            workspace_id=context.workspace_id,
            team_id=team_id,
            input={"prompt": body.prompt},
            idempotency_key=idempotency_key,
            team_repo=repo,
            agent_repo=agent_repo,
            producer=producer,
            lock_factory=lock_factory,
        )
    except TeamNotRunnableError as exc:
        if exc.reason == "Team not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            ) from exc
        # 409, not 400: the request is well-formed; the team's current
        # state is what makes it unrunnable, and the message says what to
        # change.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.reason) from exc
    except RunSubmissionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A submission with this Idempotency-Key is already in progress.",
        ) from exc
    return _session_response(session)


@router.get("/{team_id}/sessions", response_model=TeamSessionPage)
async def list_sessions_route(
    team_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None),
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> TeamSessionPage:
    await _require_team(repo, context, team_id)
    # One extra row decides `has_more` without a second count query.
    rows = await repo.list_sessions(
        workspace_id=context.workspace_id, team_id=team_id, limit=limit + 1, cursor=cursor
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return TeamSessionPage(
        data=[_session_response(s) for s in page],
        next_cursor=page[-1].created_at.isoformat() if has_more and page else None,
        has_more=has_more,
    )


@router.get("/{team_id}/sessions/{session_id}", response_model=TeamSessionResponse)
async def get_session_route(
    team_id: str,
    session_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> TeamSessionResponse:
    await _require_team(repo, context, team_id)
    return _session_response(await _require_session(repo, context, session_id))


# --- runtime reads -------------------------------------------------------


@router.get("/{team_id}/sessions/{session_id}/events", response_model=list[ExecutionEventResponse])
async def list_events_route(
    team_id: str,
    session_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> list[ExecutionEventResponse]:
    """The durable trace behind the Runtime Monitor.

    Paged by `after_sequence` rather than by offset: the client already
    knows the last sequence it rendered, and a trace stream growing
    underneath an offset would skip or repeat rows.
    """
    await _require_team(repo, context, team_id)
    await _require_session(repo, context, session_id)
    events = await repo.list_events(
        workspace_id=context.workspace_id,
        session_id=session_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return [ExecutionEventResponse(**event) for event in events]


@router.get("/{team_id}/sessions/{session_id}/handoffs", response_model=list[HandoffResponse])
async def list_handoffs_route(
    team_id: str,
    session_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> list[HandoffResponse]:
    await _require_team(repo, context, team_id)
    await _require_session(repo, context, session_id)
    return [
        HandoffResponse(
            id=h.id,
            session_id=h.session_id,
            from_agent_id=h.from_agent_id,
            to_agent_id=h.to_agent_id,
            kind=h.kind.value,
            contract=h.contract,
            reason=h.reason,
            sequence=h.sequence,
            created_at=h.created_at,
        )
        for h in await repo.list_handoffs(workspace_id=context.workspace_id, session_id=session_id)
    ]


@router.get(
    "/{team_id}/sessions/{session_id}/communications",
    response_model=list[CommunicationResponse],
)
async def list_communications_route(
    team_id: str,
    session_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> list[CommunicationResponse]:
    await _require_team(repo, context, team_id)
    await _require_session(repo, context, session_id)
    return [
        CommunicationResponse(
            id=c.id,
            session_id=c.session_id,
            from_agent_id=c.from_agent_id,
            to_agent_id=c.to_agent_id,
            kind=c.kind.value,
            content=c.content,
            sequence=c.sequence,
            created_at=c.created_at,
        )
        for c in await repo.list_communications(
            workspace_id=context.workspace_id, session_id=session_id
        )
    ]


@router.get("/{team_id}/analytics", response_model=TeamAnalyticsResponse)
async def team_analytics_route(
    team_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
) -> TeamAnalyticsResponse:
    await _require_team(repo, context, team_id)
    return TeamAnalyticsResponse(
        **await repo.team_analytics(workspace_id=context.workspace_id, team_id=team_id)
    )
