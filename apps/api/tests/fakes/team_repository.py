"""In-memory `TeamRepository` for route tests.

Stores everything keyed by workspace so tenant-isolation assertions are
structurally meaningful: a fake that ignored `workspace_id` would let a
cross-workspace test pass while the real repository leaked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from agentverse_api.orchestration_service.domain.team_entities import (
    CommunicationLogEntry,
    HandoffRecord,
    Team,
    TeamMember,
    TeamMemberRole,
    TeamSession,
    TeamSessionStatus,
    TeamTopology,
)


class FakeTeamRepository:
    def __init__(self) -> None:
        self.teams: dict[str, Team] = {}
        self.sessions: dict[str, TeamSession] = {}
        self.events: list[dict[str, Any]] = []
        self.handoffs: list[HandoffRecord] = []
        self.communications: list[CommunicationLogEntry] = []
        self.deleted: set[str] = set()

    # --- teams ---------------------------------------------------------

    async def create_team(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        topology: TeamTopology,
        objective: str | None,
        max_turns: int,
        max_cost_micro_usd: int,
        timeout_seconds: int,
        shared_memory_enabled: bool,
        shared_knowledge_base_ids: list[str],
        created_by_user_id: str,
    ) -> Team:
        now = datetime.now(UTC)
        team = Team(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            description=description,
            topology=topology,
            objective=objective,
            max_turns=max_turns,
            max_cost_micro_usd=max_cost_micro_usd,
            timeout_seconds=timeout_seconds,
            shared_memory_enabled=shared_memory_enabled,
            shared_knowledge_base_ids=list(shared_knowledge_base_ids),
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
            members=[],
        )
        self.teams[team.id] = team
        return team

    async def list_teams(self, *, workspace_id: str) -> list[Team]:
        return [
            t
            for t in self.teams.values()
            if t.workspace_id == workspace_id and t.id not in self.deleted
        ]

    async def get_team(self, *, workspace_id: str, team_id: str) -> Team | None:
        team = self.teams.get(team_id)
        if team is None or team.workspace_id != workspace_id or team_id in self.deleted:
            return None
        return team

    async def update_team(
        self, *, workspace_id: str, team_id: str, changes: dict[str, Any]
    ) -> Team | None:
        team = await self.get_team(workspace_id=workspace_id, team_id=team_id)
        if team is None:
            return None
        # `Team` is a frozen dataclass, so an update is a replacement —
        # the same discipline the real repository gets from SQL.
        updated = Team(
            **{
                **{
                    field: getattr(team, field)
                    for field in (
                        "id",
                        "workspace_id",
                        "name",
                        "description",
                        "topology",
                        "objective",
                        "max_turns",
                        "max_cost_micro_usd",
                        "timeout_seconds",
                        "shared_memory_enabled",
                        "shared_knowledge_base_ids",
                        "created_by_user_id",
                        "created_at",
                        "members",
                    )
                },
                **changes,
                "updated_at": datetime.now(UTC),
            }
        )
        self.teams[team_id] = updated
        return updated

    async def soft_delete_team(self, *, workspace_id: str, team_id: str) -> bool:
        if await self.get_team(workspace_id=workspace_id, team_id=team_id) is None:
            return False
        self.deleted.add(team_id)
        return True

    # --- members -------------------------------------------------------

    async def add_member(
        self,
        *,
        workspace_id: str,
        team_id: str,
        agent_id: str,
        role: TeamMemberRole,
        position: int,
        handoff_description: str | None,
        can_receive_handoff: bool,
    ) -> TeamMember:
        member = TeamMember(
            id=str(uuid.uuid4()),
            team_id=team_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            role=role,
            position=position,
            handoff_description=handoff_description,
            can_receive_handoff=can_receive_handoff,
            created_at=datetime.now(UTC),
        )
        self.teams[team_id].members.append(member)
        return member

    async def remove_member(self, *, workspace_id: str, team_id: str, member_id: str) -> bool:
        team = await self.get_team(workspace_id=workspace_id, team_id=team_id)
        if team is None:
            return False
        before = len(team.members)
        team.members[:] = [m for m in team.members if m.id != member_id]
        return len(team.members) < before

    async def reorder_members(
        self, *, workspace_id: str, team_id: str, member_ids_in_order: list[str]
    ) -> bool:
        team = await self.get_team(workspace_id=workspace_id, team_id=team_id)
        if team is None:
            return False
        by_id = {m.id: m for m in team.members}
        team.members[:] = [
            TeamMember(
                id=by_id[member_id].id,
                team_id=by_id[member_id].team_id,
                workspace_id=by_id[member_id].workspace_id,
                agent_id=by_id[member_id].agent_id,
                role=by_id[member_id].role,
                position=index,
                handoff_description=by_id[member_id].handoff_description,
                can_receive_handoff=by_id[member_id].can_receive_handoff,
                created_at=by_id[member_id].created_at,
            )
            for index, member_id in enumerate(member_ids_in_order)
        ]
        return True

    # --- sessions ------------------------------------------------------

    async def create_session(
        self,
        *,
        workspace_id: str,
        team_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> TeamSession:
        session = TeamSession(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            team_id=team_id,
            status=TeamSessionStatus.QUEUED,
            input=input,
            output=None,
            error_message=None,
            cost_micro_usd=None,
            total_turns=0,
            idempotency_key=idempotency_key,
            started_at=None,
            completed_at=None,
            created_at=datetime.now(UTC),
        )
        self.sessions[session.id] = session
        return session

    async def get_session(self, *, workspace_id: str, session_id: str) -> TeamSession | None:
        session = self.sessions.get(session_id)
        if session is None or session.workspace_id != workspace_id:
            return None
        return session

    async def get_session_by_idempotency_key(
        self, *, workspace_id: str, team_id: str, idempotency_key: str
    ) -> TeamSession | None:
        return next(
            (
                s
                for s in self.sessions.values()
                if s.workspace_id == workspace_id
                and s.team_id == team_id
                and s.idempotency_key == idempotency_key
            ),
            None,
        )

    async def list_sessions(
        self, *, workspace_id: str, team_id: str, limit: int, cursor: str | None
    ) -> list[TeamSession]:
        rows = sorted(
            (
                s
                for s in self.sessions.values()
                if s.workspace_id == workspace_id and s.team_id == team_id
            ),
            key=lambda s: s.created_at,
            reverse=True,
        )
        if cursor:
            boundary = datetime.fromisoformat(cursor)
            rows = [s for s in rows if s.created_at < boundary]
        return rows[:limit]

    async def update_session_status(
        self,
        *,
        workspace_id: str,
        session_id: str,
        status: TeamSessionStatus,
        error_message: str | None = None,
    ) -> bool:
        return await self.get_session(workspace_id=workspace_id, session_id=session_id) is not None

    # --- runtime reads -------------------------------------------------

    async def list_events(
        self, *, workspace_id: str, session_id: str, after_sequence: int, limit: int
    ) -> list[dict[str, Any]]:
        return [
            e
            for e in self.events
            if e["session_id"] == session_id and e["sequence"] > after_sequence
        ][:limit]

    async def list_handoffs(self, *, workspace_id: str, session_id: str) -> list[HandoffRecord]:
        return [
            h
            for h in self.handoffs
            if h.session_id == session_id and h.workspace_id == workspace_id
        ]

    async def list_communications(
        self, *, workspace_id: str, session_id: str
    ) -> list[CommunicationLogEntry]:
        return [
            c
            for c in self.communications
            if c.session_id == session_id and c.workspace_id == workspace_id
        ]

    async def team_analytics(self, *, workspace_id: str, team_id: str) -> dict[str, Any]:
        sessions = [
            s
            for s in self.sessions.values()
            if s.workspace_id == workspace_id and s.team_id == team_id
        ]
        total = len(sessions)
        cost = sum(s.cost_micro_usd or 0 for s in sessions)
        return {
            "total_sessions": total,
            "succeeded_sessions": sum(1 for s in sessions if s.status is TeamSessionStatus.SUCCESS),
            "failed_sessions": sum(1 for s in sessions if s.status is TeamSessionStatus.ERROR),
            "total_cost_micro_usd": cost,
            "total_turns": sum(s.total_turns for s in sessions),
            "total_handoffs": len([h for h in self.handoffs if h.workspace_id == workspace_id]),
            "average_cost_micro_usd": cost // total if total else 0,
        }
