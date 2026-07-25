"""In-memory fakes implementing `auth_service.domain.ports` — used by
unit tests so application-layer logic is tested without I/O
(CLAUDE.md §11). Integration tests use the real `Sql*Repository`
classes against Postgres instead; these fakes are never used there.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentverse_api.auth_service.domain.entities import (
    ApiKey,
    AuditLogEntry,
    Workspace,
    WorkspaceMember,
    WorkspaceSummary,
)
from agentverse_api.auth_service.domain.role import Role


@dataclass
class FakeWorkspaceRepository:
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    members: dict[tuple[str, str], WorkspaceMember] = field(default_factory=dict)

    async def create_workspace(self, *, name: str, slug: str, owner_user_id: str) -> Workspace:
        now = datetime.now(UTC)
        workspace = Workspace(id=str(uuid.uuid4()), name=name, slug=slug, created_at=now)
        self.workspaces[workspace.id] = workspace
        self.members[(workspace.id, owner_user_id)] = WorkspaceMember(
            workspace_id=workspace.id, user_id=owner_user_id, role=Role.OWNER, created_at=now
        )
        return workspace

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    async def list_for_user(self, user_id: str) -> list[WorkspaceSummary]:
        return [
            WorkspaceSummary(workspace=self.workspaces[workspace_id], role=member.role)
            for (workspace_id, uid), member in self.members.items()
            if uid == user_id
        ]

    async def slug_exists(self, slug: str) -> bool:
        return any(workspace.slug == slug for workspace in self.workspaces.values())

    async def get_membership(self, *, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        return self.members.get((workspace_id, user_id))

    async def add_member(self, *, workspace_id: str, user_id: str, role: Role) -> WorkspaceMember:
        member = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=role, created_at=datetime.now(UTC)
        )
        self.members[(workspace_id, user_id)] = member
        return member

    async def update_member_role(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMember:
        existing = self.members[(workspace_id, user_id)]
        updated = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=role, created_at=existing.created_at
        )
        self.members[(workspace_id, user_id)] = updated
        return updated

    async def remove_member(self, *, workspace_id: str, user_id: str) -> None:
        del self.members[(workspace_id, user_id)]

    async def count_owners(self, workspace_id: str) -> int:
        return sum(
            1
            for (wid, _uid), member in self.members.items()
            if wid == workspace_id and member.role is Role.OWNER
        )

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return [member for (wid, _uid), member in self.members.items() if wid == workspace_id]


@dataclass
class FakeApiKeyRepository:
    keys: dict[str, ApiKey] = field(default_factory=dict)

    async def create_api_key(
        self,
        *,
        workspace_id: str,
        name: str,
        key_prefix: str,
        hashed_key: str,
        created_by_user_id: str,
    ) -> ApiKey:
        key = ApiKey(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
            last_used_at=None,
            revoked_at=None,
        )
        self.keys[key.id] = key
        return key

    async def list_api_keys(self, workspace_id: str) -> list[ApiKey]:
        return [key for key in self.keys.values() if key.workspace_id == workspace_id]

    async def get_api_key(self, api_key_id: str) -> ApiKey | None:
        return self.keys.get(api_key_id)

    async def revoke_api_key(self, api_key_id: str) -> None:
        key = self.keys[api_key_id]
        self.keys[api_key_id] = ApiKey(
            id=key.id,
            workspace_id=key.workspace_id,
            name=key.name,
            key_prefix=key.key_prefix,
            hashed_key=key.hashed_key,
            created_by_user_id=key.created_by_user_id,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=datetime.now(UTC),
        )


@dataclass
class FakeAuditLogRepository:
    entries: list[AuditLogEntry] = field(default_factory=list)

    async def record(
        self,
        *,
        workspace_id: str | None,
        actor_user_id: str | None,
        action: str,
        target: str | None,
        outcome: str,
        metadata: dict[str, str],
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            outcome=outcome,
            metadata=metadata,
            created_at=datetime.now(UTC),
        )
        self.entries.append(entry)
        return entry
