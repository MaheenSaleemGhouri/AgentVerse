"""Wire schemas for the role model and tenant-defined roles."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.permission import Permission, permissions_for
from agentverse_api.auth_service.domain.role import Role, rank


class RoleDescriptor(BaseModel):
    """One built-in tier and everything it can do, inherited grants included.

    Served rather than duplicated in the frontend so the UI's permission
    matrix and the server's enforcement can never drift — there is one
    source of truth (CLAUDE.md Rule 3), and it is the server's.
    """

    role: Role
    rank: int
    permissions: list[Permission]


def describe_builtin_roles() -> list[RoleDescriptor]:
    """Every built-in role, most privileged first."""
    return [
        RoleDescriptor(role=role, rank=rank(role), permissions=sorted(permissions_for(role)))
        for role in sorted(Role, key=rank, reverse=True)
    ]


class CustomRoleResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    base_role: Role
    permissions: list[str]
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime | None


class CreateCustomRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    base_role: Role
    #: Additive grants on top of `base_role`. Validated against the
    #: `Permission` enum in the service, which raises on an unknown value
    #: rather than silently dropping it.
    permissions: list[str] = Field(default_factory=list)


class UpdateCustomRoleRequest(BaseModel):
    """Every field optional — an omitted field is left unchanged.

    `permissions` is replace-not-merge when present: a PATCH that sends
    the list sets exactly that list. Merging would make removing a grant
    impossible through this endpoint.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    base_role: Role | None = None
    permissions: list[str] | None = None
