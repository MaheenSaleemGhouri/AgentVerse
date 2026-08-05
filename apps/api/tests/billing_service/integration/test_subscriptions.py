"""Subscriptions against real Postgres.

Everything asserted here is a property of the deployed schema, not of
the Python code: the partial unique index that permits many canceled
rows but only one live one, the idempotency-key constraint that makes a
redelivered webhook a no-op, and the CHECK constraints that make a
past-due subscription without a dunning clock unrepresentable. A fake
can be written to obey those; only the database can prove it does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.domain.customer import PaymentProvider
from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier
from agentverse_api.billing_service.domain.subscription import SubscriptionStatus
from agentverse_api.billing_service.infrastructure.repositories import (
    SqlCustomerRepository,
    SqlPlanRepository,
    SqlSubscriptionRepository,
    UnknownSubscriptionFieldError,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


async def _workspace(session: AsyncSession) -> str:
    """A real workspace row, because every billing table FKs to one.

    Ownership lives in `workspace_members`, not on this table, and none
    of these assertions touch membership — so the row is deliberately
    minimal rather than dragging a user and a membership in behind it.
    """
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Billing Test', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _plan_id(session: AsyncSession, slug: PlanTier) -> str:
    result = await session.execute(
        text("SELECT id FROM plans WHERE slug = :slug"), {"slug": slug.value}
    )
    return str(result.scalar_one())


def _service(session: AsyncSession, *, now: datetime = _NOW) -> SubscriptionService:
    return SubscriptionService(
        subscriptions=SqlSubscriptionRepository(session),
        customers=SqlCustomerRepository(session),
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
        now=lambda: now,
    )


class TestLiveSubscriptionUniqueness:
    async def test_two_live_subscriptions_are_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # The application refuses this too, but the index is what makes it
        # impossible under a concurrent double-submit that the
        # application-level check races through.
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        insert = text(
            "INSERT INTO billing_subscriptions "
            "(id, workspace_id, plan_id, status, billing_interval, "
            " current_period_start, current_period_end) "
            "VALUES (gen_random_uuid(), :ws, :plan, 'active', 'monthly', "
            " now(), now() + interval '30 days')"
        )
        params = {"ws": workspace_id, "plan": plan_id}
        await db_session.execute(insert, params)
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, params)
        await db_session.rollback()

    async def test_many_canceled_rows_coexist_with_one_live_row(
        self, db_session: AsyncSession
    ) -> None:
        # The partial index has to permit this: canceled rows are the
        # workspace's billing history, and a plain unique index would
        # force deleting it.
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        for _ in range(3):
            await db_session.execute(
                text(
                    "INSERT INTO billing_subscriptions "
                    "(id, workspace_id, plan_id, status, billing_interval, "
                    " current_period_start, current_period_end, canceled_at) "
                    "VALUES (gen_random_uuid(), :ws, :plan, 'canceled', 'monthly', "
                    " now(), now() + interval '30 days', now())"
                ),
                {"ws": workspace_id, "plan": plan_id},
            )
        await db_session.execute(
            text(
                "INSERT INTO billing_subscriptions "
                "(id, workspace_id, plan_id, status, billing_interval, "
                " current_period_start, current_period_end) "
                "VALUES (gen_random_uuid(), :ws, :plan, 'active', 'monthly', "
                " now(), now() + interval '30 days')"
            ),
            {"ws": workspace_id, "plan": plan_id},
        )
        await db_session.flush()
        # And the repository returns the live one, not one of the three.
        found = await SqlSubscriptionRepository(db_session).get_for_workspace(workspace_id)
        assert found is not None
        assert found.status is SubscriptionStatus.ACTIVE
        await db_session.rollback()


class TestDatabaseInvariants:
    async def test_a_past_due_row_without_a_dunning_clock_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        # Without `past_due_since` nothing can compute when the window
        # closes, so the subscription would sit unpaid forever — the
        # failure mode `billing-expert` names explicitly.
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_subscriptions "
                    "(id, workspace_id, plan_id, status, billing_interval, "
                    " current_period_start, current_period_end) "
                    "VALUES (gen_random_uuid(), :ws, :plan, 'past_due', 'monthly', "
                    " now(), now() + interval '30 days')"
                ),
                {"ws": workspace_id, "plan": plan_id},
            )
        await db_session.rollback()

    async def test_a_canceled_row_without_a_timestamp_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_subscriptions "
                    "(id, workspace_id, plan_id, status, billing_interval, "
                    " current_period_start, current_period_end) "
                    "VALUES (gen_random_uuid(), :ws, :plan, 'canceled', 'monthly', "
                    " now(), now() + interval '30 days')"
                ),
                {"ws": workspace_id, "plan": plan_id},
            )
        await db_session.rollback()

    async def test_an_inverted_period_is_rejected(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_subscriptions "
                    "(id, workspace_id, plan_id, status, billing_interval, "
                    " current_period_start, current_period_end) "
                    "VALUES (gen_random_uuid(), :ws, :plan, 'active', 'monthly', "
                    " now(), now() - interval '1 day')"
                ),
                {"ws": workspace_id, "plan": plan_id},
            )
        await db_session.rollback()

    async def test_an_unknown_status_is_rejected(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_subscriptions "
                    "(id, workspace_id, plan_id, status, billing_interval, "
                    " current_period_start, current_period_end) "
                    "VALUES (gen_random_uuid(), :ws, :plan, 'lapsed', 'monthly', "
                    " now(), now() + interval '30 days')"
                ),
                {"ws": workspace_id, "plan": plan_id},
            )
        await db_session.rollback()

    async def test_a_plan_with_live_subscriptions_cannot_be_deleted(
        self, db_session: AsyncSession
    ) -> None:
        # ON DELETE RESTRICT. Cascading would delete paying customers'
        # subscriptions; nulling would leave rows nobody can price.
        workspace_id = await _workspace(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        await db_session.execute(
            text(
                "INSERT INTO billing_subscriptions "
                "(id, workspace_id, plan_id, status, billing_interval, "
                " current_period_start, current_period_end) "
                "VALUES (gen_random_uuid(), :ws, :plan, 'active', 'monthly', "
                " now(), now() + interval '30 days')"
            ),
            {"ws": workspace_id, "plan": plan_id},
        )
        await db_session.flush()
        with pytest.raises(IntegrityError):
            await db_session.execute(text("DELETE FROM plans WHERE id = :plan"), {"plan": plan_id})
            await db_session.flush()
        await db_session.rollback()


class TestIdempotencyKey:
    async def test_a_duplicate_key_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # The application checks first, but the constraint is what holds
        # under two concurrent deliveries of the same webhook.
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        subscription = await service.start(
            workspace_id=workspace_id,
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key=f"start-{workspace_id}",
            with_trial=False,
        )
        insert = text(
            "INSERT INTO subscription_events "
            "(id, subscription_id, workspace_id, trigger, from_status, "
            " to_status, actor, idempotency_key) "
            "VALUES (gen_random_uuid(), :sub, :ws, 'payment_failed', "
            " 'active', 'past_due', 'system', 'dup-key')"
        )
        params = {"sub": subscription.id, "ws": workspace_id}
        await db_session.execute(insert, params)
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, params)
        await db_session.rollback()

    async def test_replaying_a_transition_through_the_service_is_a_no_op(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.start(
            workspace_id=workspace_id,
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key=f"start-{workspace_id}",
            with_trial=False,
        )
        first = await service.payment_failed(workspace_id=workspace_id, idempotency_key="webhook-1")
        second = await service.payment_failed(
            workspace_id=workspace_id, idempotency_key="webhook-1"
        )
        assert second.past_due_since == first.past_due_since
        events = await service.history(workspace_id=workspace_id)
        # Creation plus one failure — not two failures.
        assert len(events) == 2
        await db_session.rollback()


class TestFieldAllowlist:
    async def test_a_transition_cannot_rewrite_the_workspace(
        self, db_session: AsyncSession
    ) -> None:
        # `changes` originates several layers up; without the allowlist a
        # well-chosen key could move a subscription between tenants.
        workspace_id = await _workspace(db_session)
        repo = SqlSubscriptionRepository(db_session)
        plan_id = await _plan_id(db_session, PlanTier.PRO)
        subscription = await repo.create(
            workspace_id=workspace_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            interval=BillingInterval.MONTHLY,
            current_period_start=_NOW,
            current_period_end=_NOW + timedelta(days=30),
            trial_end=None,
            provider_subscription_id=None,
            idempotency_key=f"create-{workspace_id}",
            actor="user-1",
        )
        from agentverse_api.billing_service.domain.subscription import SubscriptionTrigger

        with pytest.raises(UnknownSubscriptionFieldError):
            await repo.record_transition(
                subscription_id=subscription.id,
                trigger=SubscriptionTrigger.PAYMENT_FAILED,
                from_status=SubscriptionStatus.ACTIVE,
                to_status=SubscriptionStatus.PAST_DUE,
                idempotency_key="evil-1",
                actor="attacker",
                reason=None,
                metadata={},
                changes={"workspace_id": str(uuid.uuid4()), "past_due_since": _NOW},
            )
        await db_session.rollback()


class TestCustomerLinking:
    async def test_upsert_is_idempotent_under_redelivery(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        repo = SqlCustomerRepository(db_session)
        first = await repo.upsert(
            workspace_id=workspace_id,
            provider=PaymentProvider.STRIPE,
            provider_customer_id=f"cus_{workspace_id[:8]}",
            billing_email=None,
        )
        second = await repo.upsert(
            workspace_id=workspace_id,
            provider=PaymentProvider.STRIPE,
            provider_customer_id=f"cus_{workspace_id[:8]}",
            billing_email="finance@example.test",
        )
        assert second.id == first.id
        assert second.billing_email == "finance@example.test"
        await db_session.rollback()

    async def test_two_workspaces_cannot_share_a_processor_customer(
        self, db_session: AsyncSession
    ) -> None:
        # Either one's admin would otherwise be able to read the other's
        # invoices through the processor.
        first_ws = await _workspace(db_session)
        second_ws = await _workspace(db_session)
        shared = f"cus_{first_ws[:8]}"
        repo = SqlCustomerRepository(db_session)
        await repo.upsert(
            workspace_id=first_ws,
            provider=PaymentProvider.STRIPE,
            provider_customer_id=shared,
            billing_email=None,
        )
        with pytest.raises(IntegrityError):
            await repo.upsert(
                workspace_id=second_ws,
                provider=PaymentProvider.STRIPE,
                provider_customer_id=shared,
                billing_email=None,
            )
        await db_session.rollback()


class TestLifecycleEndToEnd:
    async def test_a_full_dunning_cycle_ends_in_involuntary_cancellation(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.start(
            workspace_id=workspace_id,
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key=f"start-{workspace_id}",
            with_trial=False,
        )
        await service.payment_failed(workspace_id=workspace_id, idempotency_key="webhook-fail")

        later = _service(db_session, now=_NOW + timedelta(days=15))
        canceled = await later.cancel_if_dunning_exhausted(
            workspace_id=workspace_id, idempotency_key="dunning-exhausted"
        )
        assert canceled.status is SubscriptionStatus.CANCELED
        # And the workspace now reads as having no live subscription,
        # which is what makes it fall back to Free.
        assert await later.current(workspace_id) is None
        await db_session.rollback()

    async def test_a_plan_change_lands_and_is_readable_back(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.start(
            workspace_id=workspace_id,
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key=f"start-{workspace_id}",
            with_trial=False,
        )
        mid_cycle = _service(db_session, now=_NOW + timedelta(days=15))
        updated, proration = await mid_cycle.change_plan(
            workspace_id=workspace_id,
            target_slug=PlanTier.TEAM,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        assert updated.plan_slug is PlanTier.TEAM
        assert proration.net_cents > 0
        # The join, not a cached value: read it back fresh.
        reread = await SqlSubscriptionRepository(db_session).get_for_workspace(workspace_id)
        assert reread is not None
        assert reread.plan_slug is PlanTier.TEAM
        await db_session.rollback()
