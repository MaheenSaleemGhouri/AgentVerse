"""Request/response schemas for email invitations (CLAUDE.md §7 — every
request and response is a Pydantic v2 model).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.role import Role

# A lightweight shape check, not full RFC 5322 validation — this repo has
# no `email-validator` dependency installed, and one is not worth adding
# for this single field: a malformed value simply never matches an
# existing account and produces a token no one can use, not a security
# issue.
_EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


class InviteByEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=_EMAIL_PATTERN)
    role: Role = Role.MEMBER


class InviteByEmailResponse(BaseModel):
    status: Literal["added", "invited"]
    email: str
    role: Role


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class AcceptInviteResponse(BaseModel):
    target_type: InvitationTargetType
    target_id: str
