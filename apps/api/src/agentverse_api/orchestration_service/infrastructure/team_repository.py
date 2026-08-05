"""Postgres implementation of `TeamRepository`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.sql_result import affected
from agentverse_api.orchestration_service.domain.team_entities import (
    CommunicationKind,
    CommunicationLogEntry,
    HandoffKind,
    HandoffRecord,
    Team,
    TeamMember,
    TeamMemberRole,
    TeamSession,
    TeamSessionStatus,
    TeamTopology,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    CommunicationLogModel,
    ExecutionEventModel,
    HandoffModel,
    TeamMemberModel,
    TeamModel,
    TeamSessionModel,
)


def _to_member(row: TeamMemberModel) -> TeamMember:
    return TeamMember(
        id=row.id,
        team_id=row.team_id,
        workspace_id=row.workspace_id,
        agent_id=row.agent_id,
        role=row.role,
        position=row.position,
        handoff_description=row.handoff_description,
        can_receive_handoff=row.can_receive_handoff,
        created_at=row.created_at,
    )


def _to_team(row: TeamModel, members: list[TeamMember]) -> Team:
    return Team(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        topology=row.topology,
        objective=row.objective,
        max_turns=row.max_turns,
        max_cost_micro_usd=row.max_cost_micro_usd,
        timeout_seconds=row.timeout_seconds,
        shared_memory_enabled=row.shared_memory_enabled,
        shared_knowledge_base_ids=list(row.shared_knowledge_base_ids or []),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        members=members,
    )


def _to_session(row: TeamSessionModel) -> TeamSession:
    return TeamSession(
        id=row.id,
        workspace_id=row.workspace_id,
        team_id=row.team_id,
        status=row.status,
        input=row.input,
        output=row.output,
        error_message=row.error_message,
        cost_micro_usd=row.cost_micro_usd,
        total_turns=row.total_turns,
        idempotency_key=row.idempotency_key,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


class SqlTeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- teams ---------------------------------------------------------

    def _live_teams(self, workspace_id: str) -> Select[Any]:
        return select(TeamModel).where(
            TeamModel.workspace_id == workspace_id, TeamModel.deleted_at.is_(None)
        )

    async def _members_of(self, team_ids: list[str]) -> dict[str, list[TeamMember]]:
        """One query for every team's members rather than one per team —
        the list endpoint would otherwise be N+1 against a table that
        grows with team count.
        """
        if not team_ids:
            return {}
        result = await self._session.execute(
            select(TeamMemberModel)
            .where(TeamMemberModel.team_id.in_(team_ids))
            .order_by(TeamMemberModel.position, TeamMemberModel.id)
        )
        grouped: dict[str, list[TeamMember]] = {team_id: [] for team_id in team_ids}
        for row in result.scalars():
            grouped[row.team_id].append(_to_member(row))
        return grouped

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
        model = TeamModel(
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
            shared_knowledge_base_ids=shared_knowledge_base_ids,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.commit()
        return _to_team(model, [])

    async def list_teams(self, *, workspace_id: str) -> list[Team]:
        result = await self._session.execute(
            self._live_teams(workspace_id).order_by(TeamModel.created_at.desc())
        )
        rows = list(result.scalars())
        members = await self._members_of([row.id for row in rows])
        return [_to_team(row, members.get(row.id, [])) for row in rows]

    async def count_teams(self, *, workspace_id: str) -> int:
        """Live teams, for plan-limit enforcement.

        Built from `_live_teams` rather than a fresh predicate, so
        "a team that exists" means exactly one thing across listing,
        fetching and billing (Rule 5).
        """
        result = await self._session.execute(
            select(func.count()).select_from(self._live_teams(workspace_id).subquery())
        )
        return int(result.scalar_one())

    async def get_team(self, *, workspace_id: str, team_id: str) -> Team | None:
        result = await self._session.execute(
            self._live_teams(workspace_id).where(TeamModel.id == team_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        members = await self._members_of([team_id])
        return _to_team(row, members.get(team_id, []))

    async def update_team(
        self, *, workspace_id: str, team_id: str, changes: dict[str, Any]
    ) -> Team | None:
        if not changes:
            return await self.get_team(workspace_id=workspace_id, team_id=team_id)
        await self._session.execute(
            update(TeamModel)
            .where(
                TeamModel.id == team_id,
                TeamModel.workspace_id == workspace_id,
                TeamModel.deleted_at.is_(None),
            )
            .values(**changes, updated_at=datetime.now(UTC))
        )
        await self._session.commit()
        return await self.get_team(workspace_id=workspace_id, team_id=team_id)

    async def soft_delete_team(self, *, workspace_id: str, team_id: str) -> bool:
        result = await self._session.execute(
            update(TeamModel)
            .where(
                TeamModel.id == team_id,
                TeamModel.workspace_id == workspace_id,
                TeamModel.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(UTC))
        )
        await self._session.commit()
        return affected(result)

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
        model = TeamMemberModel(
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
        self._session.add(model)
        await self._session.commit()
        return _to_member(model)

    async def remove_member(self, *, workspace_id: str, team_id: str, member_id: str) -> bool:
        result = await self._session.execute(
            delete(TeamMemberModel).where(
                TeamMemberModel.id == member_id,
                TeamMemberModel.team_id == team_id,
                TeamMemberModel.workspace_id == workspace_id,
            )
        )
        await self._session.commit()
        return affected(result)

    async def reorder_members(
        self, *, workspace_id: str, team_id: str, member_ids_in_order: list[str]
    ) -> bool:
        """All positions in one transaction.

        Positions are written as `index + 1` and then normalised, rather
        than in place, because `position` is not unique-constrained and a
        partial write would silently reorder a `sequential` team's
        execution.
        """
        for index, member_id in enumerate(member_ids_in_order):
            await self._session.execute(
                update(TeamMemberModel)
                .where(
                    TeamMemberModel.id == member_id,
                    TeamMemberModel.team_id == team_id,
                    TeamMemberModel.workspace_id == workspace_id,
                )
                .values(position=index)
            )
        await self._session.commit()
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
        model = TeamSessionModel(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            team_id=team_id,
            status=TeamSessionStatus.QUEUED,
            input=input,
            total_turns=0,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.commit()
        return _to_session(model)

    async def get_session(self, *, workspace_id: str, session_id: str) -> TeamSession | None:
        result = await self._session.execute(
            select(TeamSessionModel).where(
                TeamSessionModel.id == session_id,
                TeamSessionModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_session(row) if row else None

    async def get_session_by_idempotency_key(
        self, *, workspace_id: str, team_id: str, idempotency_key: str
    ) -> TeamSession | None:
        result = await self._session.execute(
            select(TeamSessionModel).where(
                TeamSessionModel.workspace_id == workspace_id,
                TeamSessionModel.team_id == team_id,
                TeamSessionModel.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        return _to_session(row) if row else None

    async def list_sessions(
        self, *, workspace_id: str, team_id: str, limit: int, cursor: str | None
    ) -> list[TeamSession]:
        """Cursor-based, keyed on `created_at` — session history is an
        append-mostly collection, and offset pagination on one of those
        skips or repeats rows as new sessions land mid-page (CLAUDE.md §7).
        """
        query = select(TeamSessionModel).where(
            TeamSessionModel.workspace_id == workspace_id,
            TeamSessionModel.team_id == team_id,
        )
        if cursor:
            query = query.where(TeamSessionModel.created_at < datetime.fromisoformat(cursor))
        result = await self._session.execute(
            query.order_by(TeamSessionModel.created_at.desc()).limit(limit)
        )
        return [_to_session(row) for row in result.scalars()]

    async def update_session_status(
        self,
        *,
        workspace_id: str,
        session_id: str,
        status: TeamSessionStatus,
        error_message: str | None = None,
    ) -> bool:
        values: dict[str, Any] = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if status in (
            TeamSessionStatus.SUCCESS,
            TeamSessionStatus.ERROR,
            TeamSessionStatus.CANCELLED,
        ):
            values["completed_at"] = datetime.now(UTC)
        result = await self._session.execute(
            update(TeamSessionModel)
            .where(
                TeamSessionModel.id == session_id,
                TeamSessionModel.workspace_id == workspace_id,
            )
            .values(**values)
        )
        await self._session.commit()
        return affected(result)

    # --- runtime reads -------------------------------------------------

    async def list_events(
        self, *, workspace_id: str, session_id: str, after_sequence: int, limit: int
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(ExecutionEventModel)
            .where(
                ExecutionEventModel.session_id == session_id,
                ExecutionEventModel.workspace_id == workspace_id,
                ExecutionEventModel.sequence > after_sequence,
            )
            .order_by(ExecutionEventModel.sequence)
            .limit(limit)
        )
        return [
            {
                "id": row.id,
                "type": row.event_type,
                "sequence": row.sequence,
                "agent_id": row.agent_id,
                "payload": row.payload,
                "cost_micro_usd": row.cost_micro_usd,
                "created_at": row.created_at,
            }
            for row in result.scalars()
        ]

    async def list_handoffs(self, *, workspace_id: str, session_id: str) -> list[HandoffRecord]:
        result = await self._session.execute(
            select(HandoffModel)
            .where(
                HandoffModel.session_id == session_id,
                HandoffModel.workspace_id == workspace_id,
            )
            .order_by(HandoffModel.sequence)
        )
        return [
            HandoffRecord(
                id=row.id,
                workspace_id=row.workspace_id,
                session_id=row.session_id,
                from_agent_id=row.from_agent_id,
                to_agent_id=row.to_agent_id,
                kind=HandoffKind(row.kind),
                contract=row.contract,
                reason=row.reason,
                sequence=row.sequence,
                created_at=row.created_at,
            )
            for row in result.scalars()
        ]

    async def list_communications(
        self, *, workspace_id: str, session_id: str
    ) -> list[CommunicationLogEntry]:
        result = await self._session.execute(
            select(CommunicationLogModel)
            .where(
                CommunicationLogModel.session_id == session_id,
                CommunicationLogModel.workspace_id == workspace_id,
            )
            .order_by(CommunicationLogModel.sequence)
        )
        return [
            CommunicationLogEntry(
                id=row.id,
                workspace_id=row.workspace_id,
                session_id=row.session_id,
                from_agent_id=row.from_agent_id,
                to_agent_id=row.to_agent_id,
                kind=CommunicationKind(row.kind),
                content=row.content,
                sequence=row.sequence,
                created_at=row.created_at,
            )
            for row in result.scalars()
        ]

    async def team_analytics(self, *, workspace_id: str, team_id: str) -> dict[str, Any]:
        """Five aggregates in one pass.

        Cost is summed as integer micro-USD and stays an integer all the
        way to the response (Rule 15) — an average that returned a float
        would be the first place money silently became approximate.
        """
        row = (
            (
                await self._session.execute(
                    select(
                        func.count(TeamSessionModel.id).label("total"),
                        func.count(TeamSessionModel.id)
                        .filter(TeamSessionModel.status == TeamSessionStatus.SUCCESS)
                        .label("succeeded"),
                        func.count(TeamSessionModel.id)
                        .filter(TeamSessionModel.status == TeamSessionStatus.ERROR)
                        .label("failed"),
                        func.coalesce(func.sum(TeamSessionModel.cost_micro_usd), 0).label("cost"),
                        func.coalesce(func.sum(TeamSessionModel.total_turns), 0).label("turns"),
                    ).where(
                        TeamSessionModel.workspace_id == workspace_id,
                        TeamSessionModel.team_id == team_id,
                    )
                )
            )
            .mappings()
            .one()
        )

        total = int(row["total"])
        handoff_count = (
            await self._session.scalar(
                select(func.count(HandoffModel.id))
                .select_from(HandoffModel)
                .join(TeamSessionModel, TeamSessionModel.id == HandoffModel.session_id)
                .where(
                    HandoffModel.workspace_id == workspace_id,
                    TeamSessionModel.team_id == team_id,
                )
            )
        ) or 0

        return {
            "total_sessions": total,
            "succeeded_sessions": int(row["succeeded"]),
            "failed_sessions": int(row["failed"]),
            "total_cost_micro_usd": int(row["cost"]),
            "total_turns": int(row["turns"]),
            "total_handoffs": int(handoff_count),
            # Integer division: an average cost reported as a float would
            # be the first place money stopped being exact.
            "average_cost_micro_usd": int(row["cost"]) // total if total else 0,
        }
