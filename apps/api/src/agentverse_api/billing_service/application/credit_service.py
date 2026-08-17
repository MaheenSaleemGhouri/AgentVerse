"""Granting, spending and reconciling account credit; redeeming coupons;
running the referral loop.

One service rather than three because the three share a single
invariant — every one of them ends in a movement on the credit ledger,
and splitting them would give each its own path to that ledger. A coupon
redemption and a referral payout are different *reasons*, not different
mechanisms.

**Every grant is idempotent by a key derived from its cause.** A coupon
redemption keys on `(coupon, workspace)`, a referral payout on
`(referral, side)`. A retried request or a replayed job therefore
returns the current balance rather than granting a second time — which,
for a mechanism that hands out money, is the difference between a retry
and a loss.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from agentverse_shared.observability.billing_metrics import record_credit_drift

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.domain.coupon import (
    CouponRejectedError,
    CouponRejection,
    credit_cents,
    normalize_code,
    validate,
)
from agentverse_api.billing_service.domain.credit import (
    CreditApplication,
    CreditReason,
    CreditTransaction,
    apply_credit,
)
from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier, price_cents
from agentverse_api.billing_service.domain.ports import (
    CouponRepository,
    CreditRepository,
    ReferralRepository,
)
from agentverse_api.billing_service.domain.referral import (
    REFERRAL_CREDIT_EXPIRY_DAYS,
    Referral,
    ReferralStatus,
    SelfReferralError,
    assert_transition,
    referral_code,
    resolve_reward,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class RedemptionResult:
    code: str
    credited_cents: int
    balance_cents: int


@dataclass(frozen=True, slots=True)
class CreditDrift:
    """A balance that disagrees with its own ledger.

    Reported, never auto-corrected. Rewriting a balance from a
    comparison would let a bug in the comparison silently change what
    customers owe; a human deciding each one is affordable because this
    should never fire.
    """

    workspace_id: str
    balance_cents: int
    ledger_cents: int


@dataclass(slots=True)
class CreditService:
    credits: CreditRepository
    coupons: CouponRepository
    referrals: ReferralRepository
    subscriptions: SubscriptionService
    catalog: PlanCatalogService
    now: Callable[[], datetime] = field(default=_utc_now)

    # ---- balance -----------------------------------------------------

    async def balance(self, workspace_id: str) -> int:
        return await self.credits.balance(workspace_id)

    async def history(self, *, workspace_id: str, limit: int = 50) -> list[CreditTransaction]:
        return await self.credits.history(workspace_id=workspace_id, limit=limit)

    async def grant(
        self,
        *,
        workspace_id: str,
        reason: CreditReason,
        amount_cents: int,
        description: str,
        idempotency_key: str,
        source_ref: str | None = None,
        expires_in_days: int | None = None,
    ) -> int:
        expires_at = self.now() + timedelta(days=expires_in_days) if expires_in_days else None
        return await self.credits.move(
            workspace_id=workspace_id,
            reason=reason,
            amount_cents=amount_cents,
            description=description,
            source_ref=source_ref,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    async def apply_to_invoice(
        self, *, workspace_id: str, amount_due_cents: int, invoice_ref: str
    ) -> CreditApplication:
        """Spend credit against an amount owed.

        Reads the balance, computes the application in the domain, then
        writes only if something was actually consumed — a zero-value
        ledger row is noise in the one record a customer reads to
        understand their balance.

        Keyed on the invoice, so re-running invoicing for the same period
        does not spend the credit twice.
        """
        balance = await self.credits.balance(workspace_id)
        application = apply_credit(balance_cents=balance, amount_due_cents=amount_due_cents)
        if application.applied_cents == 0:
            return application
        await self.credits.move(
            workspace_id=workspace_id,
            reason=CreditReason.INVOICE_APPLIED,
            amount_cents=application.applied_cents,
            description=f"Applied to invoice {invoice_ref}",
            source_ref=invoice_ref,
            expires_at=None,
            idempotency_key=f"invoice:{invoice_ref}:credit",
        )
        return application

    async def reconcile(self, workspace_id: str) -> CreditDrift | None:
        """Does the balance still equal its ledger?

        `None` when they agree. This should never fire — the balance is
        only ever written in the same transaction as its ledger row — so
        a finding here means something wrote a balance outside that path,
        which is worth a human looking at rather than a silent repair.
        """
        balance = await self.credits.balance(workspace_id)
        ledger = await self.credits.ledger_sum(workspace_id)
        if balance == ledger:
            return None
        # Counted as well as logged: drift means the balance projection
        # disagrees with the ledger it is derived from, which nothing
        # else in the system surfaces. Steady state is zero, so the
        # alert can be `> 0` rather than a rate.
        record_credit_drift()
        logger.error(
            "billing_credit_drift",
            extra={
                "workspace_id": workspace_id,
                "balance_cents": balance,
                "ledger_cents": ledger,
            },
        )
        return CreditDrift(workspace_id=workspace_id, balance_cents=balance, ledger_cents=ledger)

    # ---- coupons -----------------------------------------------------

    async def redeem_coupon(
        self, *, workspace_id: str, code: str, redeemed_by_user_id: str | None = None
    ) -> RedemptionResult:
        """Turn a code into account credit.

        The whole validity decision comes from `domain/coupon.validate`,
        so "why was my code rejected" has one answer computed the same
        way here and in a test. Nothing is granted until every check
        passes.
        """
        normalized = normalize_code(code)
        coupon = await self.coupons.get_by_code(normalized)
        if coupon is None:
            raise CouponRejectedError(normalized, CouponRejection.UNKNOWN)

        subscription = await self.subscriptions.current(workspace_id)
        plan_slug = subscription.plan_slug if subscription is not None else PlanTier.FREE
        interval = subscription.interval if subscription is not None else BillingInterval.MONTHLY

        rejection = validate(
            coupon=coupon,
            now=self.now(),
            plan_slug=plan_slug.value,
            already_redeemed=await self.coupons.has_redeemed(
                coupon_id=coupon.id, workspace_id=workspace_id
            ),
        )
        if rejection is not None:
            raise CouponRejectedError(normalized, rejection)

        plan = await self.catalog.get_plan(plan_slug)
        amount = credit_cents(coupon=coupon, plan_price_cents=price_cents(plan, interval))
        if amount <= 0:
            # A percentage coupon against a zero-price plan. Refused
            # rather than recorded as a redemption that granted nothing —
            # it would consume the customer's one use of the code and
            # give them no reason why.
            raise CouponRejectedError(normalized, CouponRejection.PLAN_NOT_ELIGIBLE)

        # Redemption first: its unique `(coupon, workspace)` index is
        # what makes a concurrent second attempt fail *before* any credit
        # is granted.
        await self.coupons.record_redemption(
            coupon_id=coupon.id,
            workspace_id=workspace_id,
            credited_cents=amount,
            redeemed_by_user_id=redeemed_by_user_id,
        )
        balance = await self.grant(
            workspace_id=workspace_id,
            reason=CreditReason.COUPON_REDEMPTION,
            amount_cents=amount,
            description=f"Coupon {normalized}",
            source_ref=coupon.id,
            expires_in_days=coupon.credit_expires_after_days,
            idempotency_key=f"coupon:{coupon.id}:{workspace_id}",
        )
        return RedemptionResult(code=normalized, credited_cents=amount, balance_cents=balance)

    # ---- referrals ---------------------------------------------------

    def code_for(self, workspace_id: str) -> str:
        return referral_code(workspace_id)

    async def ensure_code(self, workspace_id: str) -> str:
        """The workspace's shareable code, guaranteed indexed for reverse
        lookup by the time this returns (Phase 11: `resolve_referrer`
        needs the row to exist before anyone could plausibly have shared
        the code). Called every time a code is displayed — idempotent,
        so a second call is a no-op upsert, not a duplicate.
        """
        code = referral_code(workspace_id)
        await self.referrals.ensure_code_indexed(workspace_id=workspace_id, code=code)
        return code

    async def resolve_referrer(self, code: str) -> str | None:
        """The workspace a shareable code belongs to, or `None` for an
        unknown code — never raises, since the caller (workspace
        creation) must never fail because a pasted-in code was garbage.
        """
        return await self.referrals.resolve_referrer(code)

    async def attribute(
        self, *, referrer_workspace_id: str, referred_workspace_id: str, code: str
    ) -> Referral:
        """Record who referred whom, server-side.

        Written when the referred workspace is created, from a code
        resolved on the server. Nothing is paid here — a referral that
        paid out on signup is a bounty on creating accounts, and it would
        be collected.
        """
        if referrer_workspace_id == referred_workspace_id:
            raise SelfReferralError(referred_workspace_id)
        return await self.referrals.create(
            referrer_workspace_id=referrer_workspace_id,
            referred_workspace_id=referred_workspace_id,
            code=code,
        )

    async def qualify(self, referred_workspace_id: str) -> Referral | None:
        """Mark a referral earned. Called on the referred workspace's
        first successful payment.

        `None` when there is no referral, which is the common case —
        most workspaces are not referred, and the caller should not have
        to treat that as an error.

        Idempotent by state: a second successful payment finds the
        referral already past `PENDING` and does nothing, rather than
        qualifying it twice.
        """
        referral = await self.referrals.get_for_referred(referred_workspace_id)
        if referral is None or referral.status is not ReferralStatus.PENDING:
            return referral
        referrer_reward, referred_reward = resolve_reward(ReferralStatus.QUALIFIED)
        return await self.referrals.transition(
            referral_id=referral.id,
            status=ReferralStatus.QUALIFIED,
            referrer_reward_cents=referrer_reward,
            referred_reward_cents=referred_reward,
        )

    async def pay_out(self, referral: Referral) -> Referral:
        """Grant both sides their credit and mark the referral rewarded.

        Both grants are keyed on `(referral, side)`, so a re-run of the
        payout job returns the same balances rather than paying twice.
        The amounts come from the referral's own row, not from the
        current constants — a campaign that changes the reward must not
        retroactively change what an existing referral was promised.
        """
        assert_transition(current=referral.status, target=ReferralStatus.REWARDED)
        if referral.referrer_reward_cents > 0:
            await self.grant(
                workspace_id=referral.referrer_workspace_id,
                reason=CreditReason.REFERRAL_REWARD,
                amount_cents=referral.referrer_reward_cents,
                description="Referral reward",
                source_ref=referral.id,
                expires_in_days=REFERRAL_CREDIT_EXPIRY_DAYS,
                idempotency_key=f"referral:{referral.id}:referrer",
            )
        if referral.referred_reward_cents > 0:
            await self.grant(
                workspace_id=referral.referred_workspace_id,
                reason=CreditReason.REFERRAL_REWARD,
                amount_cents=referral.referred_reward_cents,
                description="Welcome referral credit",
                source_ref=referral.id,
                expires_in_days=REFERRAL_CREDIT_EXPIRY_DAYS,
                idempotency_key=f"referral:{referral.id}:referred",
            )
        return await self.referrals.transition(
            referral_id=referral.id, status=ReferralStatus.REWARDED
        )

    async def qualify_and_pay(self, referred_workspace_id: str) -> Referral | None:
        """The path a successful first payment takes.

        One call so the caller (M3's webhook handler) does not have to
        know the two-step shape, and so a referral cannot be left
        qualified-but-unpaid by a caller that forgot the second half.
        """
        referral = await self.qualify(referred_workspace_id)
        if referral is None or not referral.is_payable:
            return referral
        return await self.pay_out(referral)

    async def void(self, *, referral: Referral, reason: str) -> Referral:
        """Stop a referral paying out, or record that it should not have.

        Kept rather than deleted: a voided referral is evidence, and the
        ratio of voided to rewarded is how an abuse pattern becomes
        visible. Any credit already granted is clawed back by a separate,
        explicit ledger movement — not silently here, where it would be
        a balance change with no line item to explain it.
        """
        assert_transition(current=referral.status, target=ReferralStatus.VOIDED)
        return await self.referrals.transition(
            referral_id=referral.id,
            status=ReferralStatus.VOIDED,
            voided_reason=reason,
        )

    async def list_referrals(self, *, workspace_id: str, limit: int = 50) -> list[Referral]:
        return await self.referrals.list_for_referrer(
            referrer_workspace_id=workspace_id, limit=limit
        )
