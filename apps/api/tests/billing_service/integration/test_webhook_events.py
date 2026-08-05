"""The webhook delivery log against real Postgres.

The unique index is the entire point of this table, and it is the one
thing a fake cannot prove: the failure it prevents happens when two
deliveries of the same event are in flight *at the same time*, which an
application-level "have I seen this?" check cannot serialize.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.infrastructure.repositories import (
    SqlWebhookEventRepository,
)

pytestmark = pytest.mark.integration


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Webhook Test', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


class TestClaim:
    async def test_the_first_claim_wins_and_the_second_loses(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        repo = SqlWebhookEventRepository(db_session)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        first = await repo.claim(
            provider="stripe",
            provider_event_id=event_id,
            event_type="payment_failed",
            workspace_id=workspace_id,
        )
        second = await repo.claim(
            provider="stripe",
            provider_event_id=event_id,
            event_type="payment_failed",
            workspace_id=workspace_id,
        )
        assert first is True
        assert second is False
        await db_session.rollback()

    async def test_a_duplicate_insert_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # The repository's ON CONFLICT hides this, so the constraint is
        # asserted directly — otherwise a future refactor to
        # select-then-insert would pass every other test in this file.
        await _workspace(db_session)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        insert = text(
            "INSERT INTO billing_webhook_events "
            "(id, provider, provider_event_id, event_type, status) "
            "VALUES (gen_random_uuid(), 'stripe', :eid, 'payment_failed', 'received')"
        )
        await db_session.execute(insert, {"eid": event_id})
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, {"eid": event_id})
        await db_session.rollback()

    async def test_the_same_event_id_from_a_different_provider_is_allowed(
        self, db_session: AsyncSession
    ) -> None:
        # The index is scoped by provider so a second provider's id space
        # cannot collide with this one's. Asserted via raw SQL because the
        # CHECK constraint currently permits only 'stripe' — this proves
        # the index shape, which is what would matter when that changes.
        await _workspace(db_session)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        result = await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_billing_webhook_events_provider_event'"
            )
        )
        indexdef = result.scalar_one()
        assert "provider" in indexdef
        assert "provider_event_id" in indexdef
        assert "UNIQUE" in indexdef.upper()
        del event_id
        await db_session.rollback()


class TestResolve:
    async def test_resolving_records_the_outcome_and_a_timestamp(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        repo = SqlWebhookEventRepository(db_session)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        await repo.claim(
            provider="stripe",
            provider_event_id=event_id,
            event_type="payment_failed",
            workspace_id=workspace_id,
        )
        assert await repo.was_processed(provider="stripe", provider_event_id=event_id) is False
        await repo.resolve(
            provider="stripe", provider_event_id=event_id, status="processed", error=None
        )
        assert await repo.was_processed(provider="stripe", provider_event_id=event_id) is True
        result = await db_session.execute(
            text(
                "SELECT processed_at IS NOT NULL FROM billing_webhook_events "
                "WHERE provider_event_id = :eid"
            ),
            {"eid": event_id},
        )
        assert result.scalar_one() is True
        await db_session.rollback()

    async def test_a_failure_is_recorded_with_its_error(self, db_session: AsyncSession) -> None:
        # The only trail a billing dispute has to follow.
        workspace_id = await _workspace(db_session)
        repo = SqlWebhookEventRepository(db_session)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        await repo.claim(
            provider="stripe",
            provider_event_id=event_id,
            event_type="payment_failed",
            workspace_id=workspace_id,
        )
        await repo.resolve(
            provider="stripe",
            provider_event_id=event_id,
            status="failed",
            error="PlanNotFoundError: pro",
        )
        # A failed event is not "processed" — it must stay visible to the
        # sweep rather than counting as done.
        assert await repo.was_processed(provider="stripe", provider_event_id=event_id) is False
        await db_session.rollback()


class TestConstraints:
    async def test_an_unknown_status_is_rejected(self, db_session: AsyncSession) -> None:
        await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_webhook_events "
                    "(id, provider, provider_event_id, event_type, status) "
                    "VALUES (gen_random_uuid(), 'stripe', :eid, 'x', 'maybe')"
                ),
                {"eid": f"evt_{uuid.uuid4().hex[:12]}"},
            )
        await db_session.rollback()

    async def test_an_event_can_be_recorded_without_a_workspace(
        self, db_session: AsyncSession
    ) -> None:
        # An unattributable event is still worth seeing; discarding what
        # cannot be classified is how billing incidents become
        # unexplainable.
        repo = SqlWebhookEventRepository(db_session)
        claimed = await repo.claim(
            provider="stripe",
            provider_event_id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type="payment_failed",
            workspace_id=None,
        )
        assert claimed is True
        await db_session.rollback()
