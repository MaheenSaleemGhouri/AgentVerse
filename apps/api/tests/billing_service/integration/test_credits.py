"""Credits, coupons and referrals against real Postgres.

These run as integration tests rather than against fakes because every
guarantee that matters here is a database one: the row lock that stops
two concurrent spends both approving, the unique indexes that stop a
coupon becoming an unlimited credit tap and a workspace being referred
twice, and the CHECK that stops a balance going negative. A fake can be
written to obey all of them, which is exactly why proving them against a
fake proves nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.application.credit_service import CreditService
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.domain.coupon import CouponRejectedError, CouponRejection
from agentverse_api.billing_service.domain.credit import (
    CreditReason,
    InsufficientCreditError,
)
from agentverse_api.billing_service.domain.referral import (
    ReferralStatus,
    SelfReferralError,
)
from agentverse_api.billing_service.infrastructure.credit_repositories import (
    SqlCouponRepository,
    SqlCreditRepository,
    SqlReferralRepository,
)
from agentverse_api.billing_service.infrastructure.repositories import (
    SqlCustomerRepository,
    SqlPlanRepository,
    SqlSubscriptionRepository,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Credit Test', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _coupon(
    session: AsyncSession,
    *,
    kind: str = "fixed_cents",
    value: int = 2000,
    max_redemptions: int | None = None,
    valid_until: datetime | None = None,
    is_active: bool = True,
) -> tuple[str, str]:
    coupon_id = str(uuid.uuid4())
    code = f"TEST{uuid.uuid4().hex[:8].upper()}"
    await session.execute(
        text(
            "INSERT INTO billing_coupons "
            "(id, code, kind, value, max_redemptions, valid_until, is_active) "
            "VALUES (:id, :code, :kind, :value, :maxr, :until, :active)"
        ),
        {
            "id": coupon_id,
            "code": code,
            "kind": kind,
            "value": value,
            "maxr": max_redemptions,
            "until": valid_until,
            "active": is_active,
        },
    )
    await session.flush()
    return coupon_id, code


def _service(session: AsyncSession, *, now: datetime = _NOW) -> CreditService:
    catalog = PlanCatalogService(plans=SqlPlanRepository(session))
    return CreditService(
        credits=SqlCreditRepository(session),
        coupons=SqlCouponRepository(session),
        referrals=SqlReferralRepository(session),
        subscriptions=SubscriptionService(
            subscriptions=SqlSubscriptionRepository(session),
            customers=SqlCustomerRepository(session),
            catalog=catalog,
            now=lambda: now,
        ),
        catalog=catalog,
        now=lambda: now,
    )


class TestBalance:
    async def test_a_new_workspace_has_a_zero_balance(self, db_session: AsyncSession) -> None:
        # Zero, not null: every caller would otherwise have to coalesce.
        workspace_id = await _workspace(db_session)
        assert await _service(db_session).balance(workspace_id) == 0
        await db_session.rollback()

    async def test_a_grant_moves_the_balance_and_writes_a_ledger_row(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        balance = await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=1500,
            description="Launch credit",
            idempotency_key=f"grant:{workspace_id}",
        )
        assert balance == 1500
        history = await service.history(workspace_id=workspace_id)
        assert len(history) == 1
        assert history[0].balance_after_cents == 1500
        await db_session.rollback()

    async def test_a_replayed_grant_does_not_double_the_balance(
        self, db_session: AsyncSession
    ) -> None:
        # For a mechanism that hands out money, this is the difference
        # between a retry and a loss.
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        key = f"grant:{workspace_id}"
        first = await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=1500,
            description="Launch credit",
            idempotency_key=key,
        )
        second = await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=1500,
            description="Launch credit",
            idempotency_key=key,
        )
        assert first == second == 1500
        assert len(await service.history(workspace_id=workspace_id)) == 1
        await db_session.rollback()

    async def test_over_spending_is_refused(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=100,
            description="",
            idempotency_key=f"grant:{workspace_id}",
        )
        with pytest.raises(InsufficientCreditError):
            await service.grant(
                workspace_id=workspace_id,
                reason=CreditReason.INVOICE_APPLIED,
                amount_cents=200,
                description="",
                idempotency_key=f"spend:{workspace_id}",
            )
        await db_session.rollback()

    async def test_a_negative_balance_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # The domain refuses it too; this proves the deployed schema is
        # the backstop, not just the Python.
        workspace_id = await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text("INSERT INTO billing_credits (workspace_id, balance_cents) VALUES (:ws, -1)"),
                {"ws": workspace_id},
            )
        await db_session.rollback()


class TestReconciliation:
    async def test_the_balance_agrees_with_its_ledger(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=5000,
            description="",
            idempotency_key=f"a:{workspace_id}",
        )
        await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.INVOICE_APPLIED,
            amount_cents=1200,
            description="",
            idempotency_key=f"b:{workspace_id}",
        )
        assert await service.balance(workspace_id) == 3800
        assert await service.reconcile(workspace_id) is None
        await db_session.rollback()

    async def test_a_balance_written_outside_the_ledger_path_is_reported(
        self, db_session: AsyncSession
    ) -> None:
        # Should never happen — the balance is only written in the same
        # transaction as its ledger row — so a finding means something
        # bypassed that path, which is worth a human looking at.
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=1000,
            description="",
            idempotency_key=f"a:{workspace_id}",
        )
        await db_session.execute(
            text("UPDATE billing_credits SET balance_cents = 9999 WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        )
        drift = await service.reconcile(workspace_id)
        assert drift is not None
        assert drift.balance_cents == 9999
        assert drift.ledger_cents == 1000
        await db_session.rollback()


class TestCoupons:
    async def test_redeeming_grants_credit(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        _, code = await _coupon(db_session)
        result = await _service(db_session).redeem_coupon(workspace_id=workspace_id, code=code)
        assert result.credited_cents == 2000
        assert result.balance_cents == 2000
        await db_session.rollback()

    async def test_a_code_is_matched_case_insensitively(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        _, code = await _coupon(db_session)
        result = await _service(db_session).redeem_coupon(
            workspace_id=workspace_id, code=f"  {code.lower()} "
        )
        assert result.credited_cents == 2000
        await db_session.rollback()

    async def test_an_unknown_code_is_rejected_with_a_specific_reason(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        with pytest.raises(CouponRejectedError) as exc:
            await _service(db_session).redeem_coupon(workspace_id=workspace_id, code="NOPE")
        assert exc.value.rejection is CouponRejection.UNKNOWN
        await db_session.rollback()

    async def test_the_same_workspace_cannot_redeem_twice(self, db_session: AsyncSession) -> None:
        # Without this a fixed-cents coupon is an unlimited credit tap.
        workspace_id = await _workspace(db_session)
        _, code = await _coupon(db_session)
        service = _service(db_session)
        await service.redeem_coupon(workspace_id=workspace_id, code=code)
        with pytest.raises(CouponRejectedError) as exc:
            await service.redeem_coupon(workspace_id=workspace_id, code=code)
        assert exc.value.rejection is CouponRejection.ALREADY_REDEEMED
        assert await service.balance(workspace_id) == 2000
        await db_session.rollback()

    async def test_the_redemption_uniqueness_is_enforced_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        coupon_id, _ = await _coupon(db_session)
        insert = text(
            "INSERT INTO billing_coupon_redemptions "
            "(id, coupon_id, workspace_id, credited_cents) "
            "VALUES (gen_random_uuid(), :cid, :ws, 2000)"
        )
        params = {"cid": coupon_id, "ws": workspace_id}
        await db_session.execute(insert, params)
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, params)
        await db_session.rollback()

    async def test_an_exhausted_coupon_is_rejected(self, db_session: AsyncSession) -> None:
        first_ws = await _workspace(db_session)
        second_ws = await _workspace(db_session)
        _, code = await _coupon(db_session, max_redemptions=1)
        service = _service(db_session)
        await service.redeem_coupon(workspace_id=first_ws, code=code)
        with pytest.raises(CouponRejectedError) as exc:
            await service.redeem_coupon(workspace_id=second_ws, code=code)
        assert exc.value.rejection is CouponRejection.EXHAUSTED
        await db_session.rollback()

    async def test_an_expired_coupon_is_rejected(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        _, code = await _coupon(db_session, valid_until=_NOW - timedelta(days=1))
        with pytest.raises(CouponRejectedError) as exc:
            await _service(db_session).redeem_coupon(workspace_id=workspace_id, code=code)
        assert exc.value.rejection is CouponRejection.EXPIRED
        await db_session.rollback()

    async def test_an_inactive_coupon_is_rejected(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        _, code = await _coupon(db_session, is_active=False)
        with pytest.raises(CouponRejectedError) as exc:
            await _service(db_session).redeem_coupon(workspace_id=workspace_id, code=code)
        assert exc.value.rejection is CouponRejection.INACTIVE
        await db_session.rollback()

    async def test_a_percentage_coupon_against_the_free_plan_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        # Recording a redemption that granted nothing would consume the
        # customer's one use of the code and give them no reason why.
        workspace_id = await _workspace(db_session)
        _, code = await _coupon(db_session, kind="percent_off", value=50)
        with pytest.raises(CouponRejectedError):
            await _service(db_session).redeem_coupon(workspace_id=workspace_id, code=code)
        await db_session.rollback()

    async def test_a_percentage_above_one_hundred_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_coupons (id, code, kind, value) "
                    "VALUES (gen_random_uuid(), :code, 'percent_off', 150)"
                ),
                {"code": f"BAD{uuid.uuid4().hex[:6].upper()}"},
            )
        await db_session.rollback()


class TestReferrals:
    async def test_attribution_creates_a_pending_referral(self, db_session: AsyncSession) -> None:
        referrer = await _workspace(db_session)
        referred = await _workspace(db_session)
        service = _service(db_session)
        referral = await service.attribute(
            referrer_workspace_id=referrer,
            referred_workspace_id=referred,
            code=service.code_for(referrer),
        )
        assert referral.status is ReferralStatus.PENDING
        # Nothing is paid yet: a referral that pays out on signup is a
        # bounty on creating accounts.
        assert await service.balance(referrer) == 0
        await db_session.rollback()

    async def test_a_workspace_cannot_refer_itself(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        with pytest.raises(SelfReferralError):
            await service.attribute(
                referrer_workspace_id=workspace_id,
                referred_workspace_id=workspace_id,
                code=service.code_for(workspace_id),
            )
        await db_session.rollback()

    async def test_self_referral_is_also_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_referrals "
                    "(id, referrer_workspace_id, referred_workspace_id, code) "
                    "VALUES (gen_random_uuid(), :ws, :ws, 'ABCD1234')"
                ),
                {"ws": workspace_id},
            )
        await db_session.rollback()

    async def test_a_workspace_can_be_referred_only_once(self, db_session: AsyncSession) -> None:
        # Without this a code could be re-applied to farm rewards.
        first = await _workspace(db_session)
        second = await _workspace(db_session)
        referred = await _workspace(db_session)
        service = _service(db_session)
        await service.attribute(
            referrer_workspace_id=first,
            referred_workspace_id=referred,
            code=service.code_for(first),
        )
        with pytest.raises(IntegrityError):
            await service.attribute(
                referrer_workspace_id=second,
                referred_workspace_id=referred,
                code=service.code_for(second),
            )
        await db_session.rollback()

    async def test_qualifying_and_paying_credits_both_sides(self, db_session: AsyncSession) -> None:
        referrer = await _workspace(db_session)
        referred = await _workspace(db_session)
        service = _service(db_session)
        await service.attribute(
            referrer_workspace_id=referrer,
            referred_workspace_id=referred,
            code=service.code_for(referrer),
        )
        rewarded = await service.qualify_and_pay(referred)
        assert rewarded is not None
        assert rewarded.status is ReferralStatus.REWARDED
        assert await service.balance(referrer) == rewarded.referrer_reward_cents
        assert await service.balance(referred) == rewarded.referred_reward_cents
        await db_session.rollback()

    async def test_a_second_payment_does_not_pay_the_referral_twice(
        self, db_session: AsyncSession
    ) -> None:
        # A renewal must not re-trigger a payout.
        referrer = await _workspace(db_session)
        referred = await _workspace(db_session)
        service = _service(db_session)
        await service.attribute(
            referrer_workspace_id=referrer,
            referred_workspace_id=referred,
            code=service.code_for(referrer),
        )
        await service.qualify_and_pay(referred)
        balance_after_first = await service.balance(referrer)
        await service.qualify_and_pay(referred)
        assert await service.balance(referrer) == balance_after_first
        await db_session.rollback()

    async def test_a_workspace_with_no_referral_qualifies_to_nothing(
        self, db_session: AsyncSession
    ) -> None:
        # The common case — most workspaces are not referred, and the
        # caller should not have to treat that as an error.
        workspace_id = await _workspace(db_session)
        assert await _service(db_session).qualify_and_pay(workspace_id) is None
        await db_session.rollback()

    async def test_a_voided_referral_never_pays(self, db_session: AsyncSession) -> None:
        referrer = await _workspace(db_session)
        referred = await _workspace(db_session)
        service = _service(db_session)
        referral = await service.attribute(
            referrer_workspace_id=referrer,
            referred_workspace_id=referred,
            code=service.code_for(referrer),
        )
        await service.void(referral=referral, reason="suspected abuse")
        assert await service.qualify_and_pay(referred) is not None
        assert await service.balance(referrer) == 0
        await db_session.rollback()

    async def test_the_referrers_list_reports_every_status(self, db_session: AsyncSession) -> None:
        # The pending-to-rewarded ratio *is* the loop efficiency; hiding
        # the failures would make a loop that never converts look
        # perfect.
        referrer = await _workspace(db_session)
        pending = await _workspace(db_session)
        rewarded = await _workspace(db_session)
        service = _service(db_session)
        for referred in (pending, rewarded):
            await service.attribute(
                referrer_workspace_id=referrer,
                referred_workspace_id=referred,
                code=service.code_for(referrer),
            )
        await service.qualify_and_pay(rewarded)
        referrals = await service.list_referrals(workspace_id=referrer)
        statuses = {referral.status for referral in referrals}
        assert statuses == {ReferralStatus.PENDING, ReferralStatus.REWARDED}
        await db_session.rollback()


class TestInvoiceApplication:
    async def test_credit_reduces_what_an_invoice_collects(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=1000,
            description="",
            idempotency_key=f"grant:{workspace_id}",
        )
        application = await service.apply_to_invoice(
            workspace_id=workspace_id, amount_due_cents=2900, invoice_ref="inv-1"
        )
        assert application.applied_cents == 1000
        assert application.remaining_due_cents == 1900
        assert await service.balance(workspace_id) == 0
        await db_session.rollback()

    async def test_re_running_invoicing_does_not_spend_the_credit_twice(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        await service.grant(
            workspace_id=workspace_id,
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=5000,
            description="",
            idempotency_key=f"grant:{workspace_id}",
        )
        await service.apply_to_invoice(
            workspace_id=workspace_id, amount_due_cents=2000, invoice_ref="inv-1"
        )
        await service.apply_to_invoice(
            workspace_id=workspace_id, amount_due_cents=2000, invoice_ref="inv-1"
        )
        assert await service.balance(workspace_id) == 3000
        await db_session.rollback()

    async def test_no_balance_writes_no_ledger_row(self, db_session: AsyncSession) -> None:
        # A row that moves nothing is noise in the one record a customer
        # reads to understand their balance.
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        application = await service.apply_to_invoice(
            workspace_id=workspace_id, amount_due_cents=2900, invoice_ref="inv-1"
        )
        assert application.applied_cents == 0
        assert await service.history(workspace_id=workspace_id) == []
        await db_session.rollback()
