"""SQLAlchemy model for `support_tickets` (migration `5aceb34e3a0f`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.infrastructure.orm_base import Base


class SupportTicketModel(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('triaging', 'triaged', 'resolved', 'failed')",
            name="ck_support_tickets_status",
        ),
        Index("ix_support_tickets_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="triaging")
    category: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[str | None] = mapped_column(Text, default=None)
    draft_reply: Mapped[str | None] = mapped_column(Text, default=None)
    triage_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("agent_runs.id", ondelete="SET NULL"), default=None
    )
    created_by_user_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
