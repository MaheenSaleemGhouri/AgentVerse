"""Request/response schemas — every request and response is a Pydantic
v2 model, no raw dict/Any I/O (CLAUDE.md §7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.role import Role


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    #: A referrer's shareable code (Phase 11), e.g. pasted through a
    #: marketplace share link. Optional, and resolved server-side — an
    #: unknown/garbage/self-referential value never fails workspace
    #: creation, it just attributes nothing (see `create_workspace`'s
    #: route docstring).
    referral_code: str | None = Field(default=None, min_length=8, max_length=8)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    role: Role
    organization_id: str | None = None


class MemberResponse(BaseModel):
    workspace_id: str
    user_id: str
    role: Role
    created_at: datetime


class InviteMemberRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    role: Role = Role.MEMBER


class ChangeMemberRoleRequest(BaseModel):
    role: Role
