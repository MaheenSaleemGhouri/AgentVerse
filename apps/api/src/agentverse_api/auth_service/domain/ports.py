"""Repository ports (Protocols). `infrastructure/repositories.py` implements
these against Postgres; `tests/` implements them against an in-memory
fake — application-layer use cases depend only on these interfaces
(CLAUDE.md §5: infrastructure implements domain-defined ports).
"""

from __future__ import annotations

from typing import Protocol

from agentverse_api.auth_service.domain.entities import (
    ApiKey,
    AuditLogEntry,
    Workspace,
    WorkspaceMember,
    WorkspaceSummary,
)
from agentverse_api.auth_service.domain.role import Role


class WorkspaceRepository(Protocol):
    async def create_workspace(self, *, name: str, slug: str, owner_user_id: str) -> Workspace: ...

    async def get_workspace(self, workspace_id: str) -> Workspace | None: ...

    async def list_for_user(self, user_id: str) -> list[WorkspaceSummary]: ...

    async def slug_exists(self, slug: str) -> bool: ...

    async def get_membership(
        self, *, workspace_id: str, user_id: str
    ) -> WorkspaceMember | None: ...

    async def add_member(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMember: ...

    async def update_member_role(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMember: ...

    async def remove_member(self, *, workspace_id: str, user_id: str) -> None: ...

    async def count_owners(self, workspace_id: str) -> int: ...

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]: ...


class ApiKeyRepository(Protocol):
    async def create_api_key(
        self,
        *,
        workspace_id: str,
        name: str,
        key_prefix: str,
        hashed_key: str,
        created_by_user_id: str,
    ) -> ApiKey: ...

    async def list_api_keys(self, workspace_id: str) -> list[ApiKey]: ...

    async def get_api_key(self, api_key_id: str) -> ApiKey | None: ...

    async def revoke_api_key(self, api_key_id: str) -> None: ...


class AuditLogRepository(Protocol):
    async def record(
        self,
        *,
        workspace_id: str | None,
        actor_user_id: str | None,
        action: str,
        target: str | None,
        outcome: str,
        metadata: dict[str, str],
    ) -> AuditLogEntry: ...
