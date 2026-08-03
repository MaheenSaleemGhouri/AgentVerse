"""Request/response schemas for organization profile and branding.

`updated_at` is nullable and means "no settings row exists yet" — a
distinct state from a row whose every field has been cleared.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationSettingsResponse(BaseModel):
    organization_id: str
    logo_url: str | None
    brand_color: str | None
    custom_domain: str | None
    website_url: str | None
    support_email: str | None
    description: str | None
    updated_at: datetime | None
    updated_by_user_id: str | None


class UpdateOrganizationSettingsRequest(BaseModel):
    logo_url: str | None = Field(default=None, max_length=2048)
    #: Hex colour. Constrained by pattern rather than length alone so an
    #: arbitrary string can never reach a `style` attribute downstream.
    brand_color: str | None = Field(default=None, pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
    custom_domain: str | None = Field(default=None, max_length=255)
    website_url: str | None = Field(default=None, max_length=2048)
    support_email: str | None = Field(default=None, max_length=320)
    description: str | None = Field(default=None, max_length=2000)
