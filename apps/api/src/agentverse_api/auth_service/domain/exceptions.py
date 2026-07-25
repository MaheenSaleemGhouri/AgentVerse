"""Domain-level errors. The interface layer translates these to HTTP
status codes (CLAUDE.md's shared error envelope) — this layer never
imports FastAPI/Starlette to raise them directly.
"""

from __future__ import annotations

from agentverse_api.auth_service.domain.role import Role


class WorkspaceAccessDeniedError(Exception):
    """No `workspace_members` row for this (workspace_id, user_id) pair.

    Maps to HTTP 404, never 403 — existence of a workspace the caller
    isn't a member of must not be leaked (CLAUDE.md Rule 11).
    """

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"No access to workspace {workspace_id!r}")


class InsufficientRoleError(Exception):
    """Caller is a member but below the required role. Maps to HTTP 403."""

    def __init__(self, required: Role, actual: Role) -> None:
        self.required = required
        self.actual = actual
        super().__init__(f"Role {actual!r} does not satisfy required role {required!r}")


class WorkspaceSlugTakenError(Exception):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Workspace slug {slug!r} is already taken")


class UserAlreadyMemberError(Exception):
    def __init__(self, user_id: str, workspace_id: str) -> None:
        self.user_id = user_id
        self.workspace_id = workspace_id
        super().__init__(f"User {user_id!r} is already a member of workspace {workspace_id!r}")


class LastOwnerError(Exception):
    """Raised when an action would leave a workspace with zero owners."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace {workspace_id!r} must always have at least one owner")
