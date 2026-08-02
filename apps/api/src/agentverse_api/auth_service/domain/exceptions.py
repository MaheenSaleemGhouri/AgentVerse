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


class ApiKeyNotFoundError(Exception):
    """No such key, or it belongs to a different workspace than the
    caller's — both map to HTTP 404, identically, so a guessed
    cross-workspace key id cannot be distinguished from one that simply
    does not exist (CLAUDE.md Rule 11).
    """

    def __init__(self, api_key_id: str) -> None:
        self.api_key_id = api_key_id
        super().__init__(f"No API key {api_key_id!r} in this workspace")


class OrganizationSlugTakenError(Exception):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Organization slug {slug!r} is already taken")


class UserAlreadyOrgMemberError(Exception):
    def __init__(self, user_id: str, organization_id: str) -> None:
        self.user_id = user_id
        self.organization_id = organization_id
        super().__init__(
            f"User {user_id!r} is already a member of organization {organization_id!r}"
        )


class LastOrgOwnerError(Exception):
    """Raised when an action would leave an organization with zero owners."""

    def __init__(self, organization_id: str) -> None:
        self.organization_id = organization_id
        super().__init__(f"Organization {organization_id!r} must always have at least one owner")


class InvitationNotFoundError(Exception):
    """No `verifications` row for this token, or it isn't an invitation
    row at all — maps to HTTP 404, identically, so a guessed token cannot
    be distinguished from a real but unrelated verification row.
    """

    def __init__(self) -> None:
        super().__init__("Invitation not found")


class InvitationAlreadyConsumedError(Exception):
    def __init__(self) -> None:
        super().__init__("This invitation has already been used")


class InvitationExpiredError(Exception):
    def __init__(self) -> None:
        super().__init__("This invitation has expired")


class InvitationEmailMismatchError(Exception):
    """The accepting identity's verified email does not match the email
    the invitation was sent to — prevents one account from consuming an
    invite addressed to someone else's inbox.
    """

    def __init__(self) -> None:
        super().__init__("This invitation was sent to a different email address")


class InvalidCidrError(Exception):
    """The submitted allowlist entry isn't a parseable IPv4/IPv6 network."""

    def __init__(self, cidr: str) -> None:
        self.cidr = cidr
        super().__init__(f"{cidr!r} is not a valid IP address or CIDR range")
