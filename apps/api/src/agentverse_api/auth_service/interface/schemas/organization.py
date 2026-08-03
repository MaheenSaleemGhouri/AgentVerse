"""Request/response schemas for `/api/v1/organizations` — every request
and response is a Pydantic v2 model, no raw dict/Any I/O (CLAUDE.md §7).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.role import Role


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RenameOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    role: Role


class OrganizationMemberResponse(BaseModel):
    organization_id: str
    user_id: str
    role: Role
    suspended_at: datetime | None
    created_at: datetime


class InviteOrgMemberRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    role: Role = Role.MEMBER


class ChangeOrgMemberRoleRequest(BaseModel):
    role: Role


class OrganizationWorkspaceResponse(BaseModel):
    """A workspace attached to an organization — deliberately carries no
    role: attachment grants no workspace access, so there is no role to
    report here (ADR-0011). See `WorkspaceResponse` for the caller's own
    workspace-scoped role.
    """

    id: str
    name: str
    slug: str
    created_at: datetime
