"""Request/response schemas for `/resource-permissions` (CLAUDE.md §7 —
every request and response is a Pydantic v2 model).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GrantResourcePermissionRequest(BaseModel):
    resource_type: str = Field(min_length=1, max_length=50)
    #: `""` (the default) means "every resource of `resource_type`" —
    #: the right default for workspace-wide types like `billing`.
    resource_id: str = Field(default="", max_length=100)
    principal_id: str = Field(min_length=1, max_length=255)
    permission: str = Field(min_length=1, max_length=50)


class ResourcePermissionResponse(BaseModel):
    id: str
    workspace_id: str
    resource_type: str
    resource_id: str
    principal_type: str
    principal_id: str
    permission: str
    granted_by_user_id: str
    created_at: datetime
