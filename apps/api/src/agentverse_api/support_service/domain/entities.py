"""Support-ticket domain entities — plain dataclasses, zero framework/ORM
imports (CLAUDE.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TicketStatus(StrEnum):
    #: A triage run has been submitted; its output has not been read yet.
    TRIAGING = "triaging"
    #: The triage run completed and its structured output was parsed.
    TRIAGED = "triaged"
    #: A human closed the ticket. Set explicitly, never inferred.
    RESOLVED = "resolved"
    #: The triage run failed, or its output could not be parsed — never
    #: left silently stuck on `TRIAGING` forever.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SupportTicket:
    id: str
    workspace_id: str
    subject: str
    body: str
    status: TicketStatus
    category: str | None
    priority: str | None
    confidence: str | None
    draft_reply: str | None
    triage_run_id: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime
