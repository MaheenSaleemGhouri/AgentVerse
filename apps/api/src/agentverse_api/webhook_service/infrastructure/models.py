"""Webhook ORM models.

Two tenant-owned tables, both `workspace_id`-scoped in the ordinary way.

`webhook_deliveries` is the durable queue. It is a table rather than a
Redis stream because a delivery that must survive six retries over two
hours has to outlive a worker restart, and Redis is never the system of
record (Rule 13). The worker claims due rows with `FOR UPDATE SKIP
LOCKED`, so several replicas drain the same table without coordinating
and without any one of them blocking the others.

The signing secret is stored under the envelope vault
(`agentverse_shared.security.envelope`) rather than hashed: unlike an API
key, the customer needs to *read* it again to configure their verifier,
so it must be decryptable. Same construction as MCP credentials and SSO
client secrets — one crypto implementation for the platform, not three.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, LargeBinary, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.infrastructure.orm_base import Base

_STATUSES = "('pending', 'delivering', 'delivered', 'failed')"


class WebhookEndpointModel(Base):
    """One customer URL and its subscriptions."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        # The dispatch query: active endpoints in this workspace. Leads
        # with `workspace_id` per §8 — unlike the marketplace catalog,
        # this is an ordinary tenant-scoped read.
        Index("ix_webhook_endpoints_workspace", "workspace_id", "is_active"),
        CheckConstraint(
            "consecutive_failures >= 0", name="ck_webhook_endpoints_failures_non_negative"
        ),
        # A URL is required and must be absolute. Checked in the database
        # as well as the schema because a row inserted by a migration or
        # a fixture bypasses Pydantic, and an endpoint with a relative
        # URL fails at delivery time rather than at write time.
        CheckConstraint(
            "url LIKE 'http://%' OR url LIKE 'https://%'", name="ck_webhook_url_scheme"
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    # A Postgres array rather than a join table: the set is small, always
    # read whole, and never queried by "which endpoints want event X"
    # across workspaces — dispatch already has the workspace in hand.
    events: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Sealed, not hashed: the customer must be able to read it back to
    # configure their verifier, which a one-way hash would prevent.
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Reset on any success. An endpoint with intermittent trouble is
    # never disabled — only one that has stopped answering entirely.
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    disabled_at: Mapped[datetime | None] = mapped_column(default=None)
    disabled_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class WebhookDeliveryModel(Base):
    """One attempt-set at delivering one event to one endpoint.

    The durable queue. A table rather than a Redis stream because a
    delivery retried over two hours must survive a worker restart, and
    Redis is never the system of record (Rule 13).
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint(f"status IN {_STATUSES}", name="ck_webhook_deliveries_status"),
        CheckConstraint("attempts >= 0", name="ck_webhook_deliveries_attempts_non_negative"),
        # One delivery per (endpoint, event occurrence). The dispatcher
        # derives `event_id` from the source row that caused it, so a
        # retried dispatch — a worker redelivery, a replayed job —
        # produces the same key and is absorbed by this index rather than
        # sending the customer a duplicate (Rule 14).
        Index(
            "uq_webhook_deliveries_event",
            "endpoint_id",
            "event_id",
            unique=True,
        ),
        # The drainer's query: what is due now, oldest first. Partial, so
        # the index stays proportional to the backlog rather than to the
        # delivery history — which is append-only and never shrinks.
        Index(
            "ix_webhook_deliveries_due",
            "next_attempt_at",
            postgresql_where="status = 'pending'",
        ),
        Index("ix_webhook_deliveries_workspace", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    endpoint_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(Text, index=True)
    #: Derived from the source row, never random — that is what makes a
    #: redelivered dispatch idempotent.
    event_id: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_response_status: Mapped[int | None] = mapped_column(Integer, default=None)
    # Truncated before storage. An endpoint returning a megabyte of HTML
    # on every failure would otherwise put it in this table six times.
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
