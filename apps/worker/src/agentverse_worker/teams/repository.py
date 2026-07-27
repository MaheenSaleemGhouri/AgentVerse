"""Narrow read/write access to the team tables for the topology
executors — not a general-purpose repository, just what a running team
session needs.

Reads resolve a team plus its members plus each member's *published*
agent version, because a team composes agents rather than redefining
them (ADR-0009). Writes are the four things a session produces: status
transitions, handoff records, communication log entries, and trace
events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.agents.tables import agent_versions_table
from agentverse_worker.teams.tables import (
    agents_table,
    communication_logs_table,
    execution_events_table,
    handoffs_table,
    team_members_table,
    team_sessions_table,
    teams_table,
)


@dataclass(frozen=True, slots=True)
class MemberRecord:
    """A seat on the team, resolved together with the agent version that
    fills it. `config` is the agent's own published configuration — the
    team contributes only `role`, `position`, `handoff_description`, and
    `can_receive_handoff`.
    """

    member_id: str
    agent_id: str
    agent_name: str
    role: str
    position: int
    handoff_description: str | None
    can_receive_handoff: bool
    agent_version_id: str
    config: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TeamRecord:
    id: str
    workspace_id: str
    name: str
    topology: str
    objective: str | None
    max_turns: int
    max_cost_micro_usd: int
    timeout_seconds: int
    shared_memory_enabled: bool
    shared_knowledge_base_ids: list[str] = field(default_factory=list)
    members: list[MemberRecord] = field(default_factory=list)

    def ordered_members(self) -> list[MemberRecord]:
        return sorted(self.members, key=lambda m: (m.position, m.member_id))

    def by_role(self, role: str) -> MemberRecord | None:
        return next((m for m in self.ordered_members() if m.role == role), None)

    def workers(self) -> list[MemberRecord]:
        """Everyone the supervisor may delegate to.

        Excludes the supervisor itself (an agent handing off to itself is
        an unbounded loop the step ceiling would have to catch) and any
        member whose seat opted out of automatic handoff.
        """
        return [
            m for m in self.ordered_members() if m.role != "supervisor" and m.can_receive_handoff
        ]


@dataclass(frozen=True, slots=True)
class TeamSessionRecord:
    id: str
    workspace_id: str
    team_id: str
    status: str
    input: dict[str, Any]


class TeamRepositoryProtocol(Protocol):
    """The executors depend on this rather than the concrete class, so
    topology logic is unit-testable against an in-memory fake without a
    live Postgres (CLAUDE.md §11).
    """

    async def get_session(self, session_id: str) -> TeamSessionRecord | None: ...
    async def get_team(self, team_id: str, *, workspace_id: str) -> TeamRecord | None: ...
    async def update_session_status(
        self,
        *,
        session_id: str,
        status: str,
        output: str | None = None,
        error_message: str | None = None,
        cost_micro_usd: int | None = None,
        total_turns: int | None = None,
    ) -> None: ...
    async def record_handoff(
        self,
        *,
        session_id: str,
        workspace_id: str,
        from_agent_id: str | None,
        to_agent_id: str,
        kind: str,
        contract: dict[str, Any],
        reason: str | None,
        sequence: int,
    ) -> str: ...
    async def record_communication(
        self,
        *,
        session_id: str,
        workspace_id: str,
        from_agent_id: str | None,
        to_agent_id: str | None,
        kind: str,
        content: dict[str, Any],
        sequence: int,
    ) -> None: ...
    async def record_event(
        self,
        *,
        session_id: str,
        workspace_id: str,
        event_type: str,
        agent_id: str | None,
        sequence: int,
        payload: dict[str, Any],
        cost_micro_usd: int | None,
    ) -> None: ...


class WorkerTeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session(self, session_id: str) -> TeamSessionRecord | None:
        result = await self._session.execute(
            select(team_sessions_table).where(team_sessions_table.c.id == session_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return TeamSessionRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            team_id=row["team_id"],
            status=row["status"],
            input=row["input"],
        )

    async def get_team(self, team_id: str, *, workspace_id: str) -> TeamRecord | None:
        """Workspace-scoped by construction (Rule 11) — a team id alone
        is never enough to load a team, so a session row pointing at
        another tenant's team resolves to nothing rather than to data.
        """
        result = await self._session.execute(
            select(teams_table).where(
                (teams_table.c.id == team_id)
                & (teams_table.c.workspace_id == workspace_id)
                & teams_table.c.deleted_at.is_(None)
            )
        )
        team_row = result.mappings().one_or_none()
        if team_row is None:
            return None

        # Members joined to the agent's *published* version. A member
        # whose agent has never been published is dropped rather than
        # run against a draft: a team must not execute configuration the
        # user has not published (Phase 4's own rule, inherited here).
        member_rows = await self._session.execute(
            select(
                team_members_table.c.id.label("member_id"),
                team_members_table.c.agent_id,
                team_members_table.c.role,
                team_members_table.c.position,
                team_members_table.c.handoff_description,
                team_members_table.c.can_receive_handoff,
                agent_versions_table.c.id.label("agent_version_id"),
                agent_versions_table.c.config,
            )
            .select_from(
                team_members_table.join(
                    agents_table, team_members_table.c.agent_id == agents_table.c.id
                ).join(
                    agent_versions_table,
                    agent_versions_table.c.id == agents_table.c.published_version_id,
                )
            )
            .where(
                (team_members_table.c.team_id == team_id)
                & (team_members_table.c.workspace_id == workspace_id)
            )
            .order_by(team_members_table.c.position)
        )

        members = [
            MemberRecord(
                member_id=row["member_id"],
                agent_id=row["agent_id"],
                agent_name=str(row["config"].get("name") or f"agent-{row['agent_id'][:8]}"),
                role=row["role"],
                position=row["position"],
                handoff_description=row["handoff_description"],
                can_receive_handoff=row["can_receive_handoff"],
                agent_version_id=row["agent_version_id"],
                config=row["config"],
            )
            for row in member_rows.mappings()
        ]

        return TeamRecord(
            id=team_row["id"],
            workspace_id=team_row["workspace_id"],
            name=team_row["name"],
            topology=team_row["topology"],
            objective=team_row["objective"],
            max_turns=team_row["max_turns"],
            max_cost_micro_usd=team_row["max_cost_micro_usd"],
            timeout_seconds=team_row["timeout_seconds"],
            shared_memory_enabled=team_row["shared_memory_enabled"],
            shared_knowledge_base_ids=list(team_row["shared_knowledge_base_ids"] or []),
            members=members,
        )

    async def update_session_status(
        self,
        *,
        session_id: str,
        status: str,
        output: str | None = None,
        error_message: str | None = None,
        cost_micro_usd: int | None = None,
        total_turns: int | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        now = datetime.now(UTC)
        if status == "running":
            values["started_at"] = now
        if status in ("success", "error", "cancelled"):
            values["completed_at"] = now
        if output is not None:
            values["output"] = output
        if error_message is not None:
            values["error_message"] = error_message
        if cost_micro_usd is not None:
            values["cost_micro_usd"] = cost_micro_usd
        if total_turns is not None:
            values["total_turns"] = total_turns
        await self._session.execute(
            update(team_sessions_table)
            .where(team_sessions_table.c.id == session_id)
            .values(**values)
        )
        await self._session.commit()

    async def record_handoff(
        self,
        *,
        session_id: str,
        workspace_id: str,
        from_agent_id: str | None,
        to_agent_id: str,
        kind: str,
        contract: dict[str, Any],
        reason: str | None,
        sequence: int,
    ) -> str:
        handoff_id = str(uuid.uuid4())
        await self._session.execute(
            handoffs_table.insert().values(
                id=handoff_id,
                workspace_id=workspace_id,
                session_id=session_id,
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                kind=kind,
                contract=contract,
                reason=reason,
                sequence=sequence,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.commit()
        return handoff_id

    async def record_communication(
        self,
        *,
        session_id: str,
        workspace_id: str,
        from_agent_id: str | None,
        to_agent_id: str | None,
        kind: str,
        content: dict[str, Any],
        sequence: int,
    ) -> None:
        await self._session.execute(
            communication_logs_table.insert().values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                session_id=session_id,
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                kind=kind,
                content=content,
                sequence=sequence,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.commit()

    async def record_event(
        self,
        *,
        session_id: str,
        workspace_id: str,
        event_type: str,
        agent_id: str | None,
        sequence: int,
        payload: dict[str, Any],
        cost_micro_usd: int | None,
    ) -> None:
        await self._session.execute(
            execution_events_table.insert().values(
                id=str(uuid.uuid4()),
                created_at=datetime.now(UTC),
                session_id=session_id,
                workspace_id=workspace_id,
                event_type=event_type,
                agent_id=agent_id,
                sequence=sequence,
                payload=payload,
                cost_micro_usd=cost_micro_usd,
            )
        )
        await self._session.commit()
