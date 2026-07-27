"""Repository port for the multi-agent team tables.

Every method takes `workspace_id` and every implementation must filter
by it (Rule 11). It is a required keyword rather than something the
implementation could derive, so a caller cannot accidentally omit it and
a reviewer can see the scoping at the call site.
"""

from __future__ import annotations

from typing import Any, Protocol

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


class TeamRepository(Protocol):
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
    ) -> Team: ...

    async def list_teams(self, *, workspace_id: str) -> list[Team]: ...

    async def get_team(self, *, workspace_id: str, team_id: str) -> Team | None: ...

    async def update_team(
        self, *, workspace_id: str, team_id: str, changes: dict[str, Any]
    ) -> Team | None: ...

    async def soft_delete_team(self, *, workspace_id: str, team_id: str) -> bool:
        """Soft delete, matching every other user-facing entity. A team
        with session history must remain resolvable so those sessions
        still render.
        """
        ...

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
    ) -> TeamMember: ...

    async def remove_member(self, *, workspace_id: str, team_id: str, member_id: str) -> bool: ...

    async def reorder_members(
        self, *, workspace_id: str, team_id: str, member_ids_in_order: list[str]
    ) -> bool:
        """Applies drag-and-drop ordering as one write.

        One statement per position would leave the team half-reordered if
        it failed midway, and for a `sequential` team that is a changed
        execution order rather than a cosmetic glitch.
        """
        ...

    # --- sessions ------------------------------------------------------
    async def create_session(
        self,
        *,
        workspace_id: str,
        team_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> TeamSession: ...

    async def get_session(self, *, workspace_id: str, session_id: str) -> TeamSession | None: ...

    async def get_session_by_idempotency_key(
        self, *, workspace_id: str, team_id: str, idempotency_key: str
    ) -> TeamSession | None: ...

    async def list_sessions(
        self, *, workspace_id: str, team_id: str, limit: int, cursor: str | None
    ) -> list[TeamSession]: ...

    # --- runtime reads -------------------------------------------------
    async def list_events(
        self, *, workspace_id: str, session_id: str, after_sequence: int, limit: int
    ) -> list[dict[str, Any]]: ...

    async def list_handoffs(self, *, workspace_id: str, session_id: str) -> list[HandoffRecord]: ...

    async def list_communications(
        self, *, workspace_id: str, session_id: str
    ) -> list[CommunicationLogEntry]: ...

    async def team_analytics(self, *, workspace_id: str, team_id: str) -> dict[str, Any]:
        """Aggregates over `team_sessions` for one team.

        Computed in Postgres rather than by loading sessions and summing
        in Python: a team with thousands of sessions would otherwise pull
        every row into the API process to produce five numbers.
        """
        ...

    async def update_session_status(
        self,
        *,
        workspace_id: str,
        session_id: str,
        status: TeamSessionStatus,
        error_message: str | None = None,
    ) -> bool: ...
