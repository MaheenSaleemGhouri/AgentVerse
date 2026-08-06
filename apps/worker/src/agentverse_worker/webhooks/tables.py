"""SQLAlchemy Core mirrors of the webhook tables the drainer touches.

Same "shared wire contract, not shared code" pattern as
`retention/tables.py` and `mcp/tables.py`: apps/api's Alembic migrations
are the one source of truth for the schema, and this worker declares
only the columns it reads or writes.

`payload` is here and `secret_ciphertext` is too, because delivery needs
both — the body to send and the secret to sign it with. The worker
decrypts through the same `CredentialVault` apps/api sealed with; the
key ring comes from the environment on both sides, so neither service
holds the other's copy of anything.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

metadata = MetaData()

webhook_endpoints_table = Table(
    "webhook_endpoints",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False), nullable=False),
    Column("url", Text, nullable=False),
    Column("events", ARRAY(Text), nullable=False),
    Column("secret_ciphertext", LargeBinary, nullable=False),
    Column("wrapped_dek", LargeBinary, nullable=False),
    Column("key_version", Text, nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("consecutive_failures", Integer, nullable=False),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
    Column("disabled_reason", Text, nullable=True),
)

webhook_deliveries_table = Table(
    "webhook_deliveries",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False), nullable=False),
    Column("endpoint_id", UUID(as_uuid=False), nullable=False),
    Column("event_type", Text, nullable=False),
    Column("event_id", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("status", Text, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("last_response_status", Integer, nullable=True),
    Column("last_error", Text, nullable=True),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
)
