"""Request/response schemas — every request and response is a Pydantic
v2 model (CLAUDE.md §7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.support_service.application.support_ticket_service import MAX_BODY_LENGTH


class CreateSupportTicketRequest(BaseModel):
    #: Which installed agent triages this ticket — usually the seeded
    #: `support-triage` template, but not hardcoded: a workspace may
    #: install and use a different triage agent.
    agent_id: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=MAX_BODY_LENGTH)


class SupportTicketResponse(BaseModel):
    id: str
    workspace_id: str
    subject: str
    body: str
    status: str
    category: str | None
    priority: str | None
    confidence: str | None
    draft_reply: str | None
    triage_run_id: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class SupportTicketPage(BaseModel):
    data: list[SupportTicketResponse]
    next_cursor: str | None
    has_more: bool
