"""`audit_logs` is append-only at the database level (Phase 12,
migration `9011ed21fa17`) — not just by `AuditService` never exposing an
update/delete method. This test deliberately bypasses the application
layer entirely (raw SQL against the table) to prove the guarantee holds
even for a caller that doesn't go through `AuditService` at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.infrastructure.repositories import SqlAuditLogRepository

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, name: str) -> str:
    user_id = f"user-{name}"
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{name}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return user_id


async def test_a_raw_update_against_audit_logs_is_rejected(
    db_session: AsyncSession, unique_name: str
) -> None:
    actor = await _make_user(db_session, unique_name)
    entry = await SqlAuditLogRepository(db_session).record(
        workspace_id=None,
        actor_user_id=actor,
        action="test.immutability_probe",
        target=None,
        outcome="success",
        metadata={},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(
            text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"),
            {"id": entry.id},
        )
    await db_session.rollback()


async def test_a_raw_delete_against_audit_logs_is_rejected(
    db_session: AsyncSession, unique_name: str
) -> None:
    actor = await _make_user(db_session, unique_name)
    entry = await SqlAuditLogRepository(db_session).record(
        workspace_id=None,
        actor_user_id=actor,
        action="test.immutability_probe",
        target=None,
        outcome="success",
        metadata={},
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": entry.id})
    await db_session.rollback()

    # Genuinely survived, not just "the failed statement rolled back" —
    # re-query on a fresh statement after the rollback.
    row = await db_session.execute(
        text("SELECT 1 FROM audit_logs WHERE id = :id"), {"id": entry.id}
    )
    assert row.scalar() == 1
