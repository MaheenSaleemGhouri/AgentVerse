"""Assistant ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.infrastructure.orm_base import Base


class AssistantSessionModel(Base):
    """One help conversation.

    Carries both `workspace_id` (Rule 11, no exceptions) and `user_id`.
    The second is not redundant: billing and quota are facts about a
    workspace, but a half-typed question is personal, and a workspace
    admin reading their colleagues' support conversations is a privacy
    surprise nobody asked for.
    """

    __tablename__ = "assistant_sessions"
    __table_args__ = (
        # The sidebar's only query: my recent sessions in this workspace,
        # most recently active first.
        Index(
            "ix_assistant_sessions_owner",
            "workspace_id",
            "user_id",
            "last_message_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # TEXT, not UUID: `users.id` is issued by the auth provider, not by
    # Postgres, and is not a UUID. Matching it is a hard requirement —
    # the foreign key simply will not build otherwise.
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AssistantMessageModel(Base):
    """One turn.

    Deliberately has no `workspace_id` of its own. It is reachable only
    through its session, and the session is always loaded workspace- and
    user-scoped first — a denormalised copy here would be a second thing
    to keep true, and the first one to go stale.
    """

    __tablename__ = "assistant_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_assistant_messages_role"),
        Index("ix_assistant_messages_session", "session_id", "seq"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # The ordering key, and the reason it is not `created_at`: `now()` is
    # transaction-start time, so two rows written in one transaction
    # carry the same timestamp and fall back to comparing random UUIDs.
    # That reordered a conversation in the integration test that caught
    # it. An identity column is monotonic regardless of clock resolution
    # or transaction boundaries.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("assistant_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
