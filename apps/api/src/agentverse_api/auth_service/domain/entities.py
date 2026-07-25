"""Workspace/RBAC domain entities — plain dataclasses, no ORM/framework coupling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_api.auth_service.domain.role import Role


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    slug: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    workspace_id: str
    user_id: str
    role: Role
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    """A workspace plus the calling user's role in it — the workspace
    switcher's list view. Distinct from `Workspace` (no implicit role)
    so a workspace fetched without a resolved caller can't accidentally
    be treated as if it carried role information.
    """

    workspace: Workspace
    role: Role


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Resolved by `get_current_workspace` — the only trusted answer to
    "does this identity have access to this workspace, and at what role."
    """

    workspace_id: str
    user_id: str
    role: Role


@dataclass(frozen=True, slots=True)
class ApiKey:
    id: str
    workspace_id: str
    name: str
    key_prefix: str
    hashed_key: str
    created_by_user_id: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    id: str
    workspace_id: str | None
    actor_user_id: str | None
    action: str
    target: str | None
    outcome: str
    metadata: dict[str, str]
    created_at: datetime
