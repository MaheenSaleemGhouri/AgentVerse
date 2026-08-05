"""Postgres adapters for credits, coupons and referrals.

Split from `repositories.py` because that file already carries plans,
subscriptions, webhooks and usage; a single module holding every adapter
in the context stops being navigable somewhere around the fifth.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.domain.coupon import Coupon, DiscountKind, normalize_code
from agentverse_api.billing_service.domain.credit import (
    CreditReason,
    CreditTransaction,
    is_credit,
    next_balance,
)
from agentverse_api.billing_service.domain.referral import Referral, ReferralStatus
from agentverse_api.billing_service.infrastructure.models import (
    CouponModel,
    CouponRedemptionModel,
    CreditBalanceModel,
    CreditTransactionModel,
    ReferralModel,
)


class SqlCreditRepository:
    """Implements `domain.ports.CreditRepository`.

    The load-bearing detail is `with_for_update()` in `move`: without it
    two concurrent spends each read the same balance and both approve,
    which is how a workspace spends credit it does not have.
    `postgresql-expert` prescribes exactly this for balance decrements.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def balance(self, workspace_id: str) -> int:
        result = await self._session.execute(
            select(CreditBalanceModel.balance_cents).where(
                CreditBalanceModel.workspace_id == workspace_id
            )
        )
        # Zero, not `None`: a workspace that has never held credit has a
        # balance of zero, and every caller would otherwise have to
        # coalesce it themselves.
        return int(result.scalar_one_or_none() or 0)

    async def move(
        self,
        *,
        workspace_id: str,
        reason: CreditReason,
        amount_cents: int,
        description: str,
        source_ref: str | None,
        expires_at: datetime | None,
        idempotency_key: str,
    ) -> int:
        # Replay check first: a redelivered grant should return the
        # current balance, not fail a constraint and surface as a 500 for
        # a delivery guarantee working as designed.
        seen = await self._session.execute(
            select(CreditTransactionModel.id).where(
                CreditTransactionModel.idempotency_key == idempotency_key
            )
        )
        if seen.scalar_one_or_none() is not None:
            return await self.balance(workspace_id)

        # Ensure the balance row exists before locking it. ON CONFLICT DO
        # NOTHING rather than a read-then-insert, because two first-ever
        # grants can race and the read-then-insert version loses.
        await self._session.execute(
            pg_insert(CreditBalanceModel)
            .values(workspace_id=workspace_id, balance_cents=0)
            .on_conflict_do_nothing(index_elements=[CreditBalanceModel.workspace_id])
        )
        locked = await self._session.execute(
            select(CreditBalanceModel)
            .where(CreditBalanceModel.workspace_id == workspace_id)
            .with_for_update()
        )
        row = locked.scalar_one()

        # The domain decides — including refusing to go negative. Doing
        # the arithmetic here would put the one rule that protects real
        # money in a file with no tests of its own.
        updated_balance = next_balance(
            balance_cents=row.balance_cents, reason=reason, amount_cents=amount_cents
        )
        row.balance_cents = updated_balance
        self._session.add(
            CreditTransactionModel(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                reason=reason.value,
                amount_cents=amount_cents,
                balance_after_cents=updated_balance,
                description=description,
                source_ref=source_ref,
                expires_at=expires_at,
                idempotency_key=idempotency_key,
            )
        )
        await self._session.flush()
        return updated_balance

    async def history(self, *, workspace_id: str, limit: int) -> list[CreditTransaction]:
        result = await self._session.execute(
            select(CreditTransactionModel)
            .where(CreditTransactionModel.workspace_id == workspace_id)
            .order_by(CreditTransactionModel.created_at.desc())
            .limit(limit)
        )
        return [_to_transaction(row) for row in result.scalars().all()]

    async def ledger_sum(self, workspace_id: str) -> int:
        """Re-derive the balance from the ledger.

        Summed in SQL with a CASE on the reason rather than in Python:
        the ledger only grows, and pulling every row back to add them up
        would eventually move a workspace's whole history over the wire
        to compute one number.
        """
        result = await self._session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                CreditTransactionModel.reason.in_(
                                    [r.value for r in CreditReason if is_credit(r)]
                                ),
                                CreditTransactionModel.amount_cents,
                            ),
                            else_=-CreditTransactionModel.amount_cents,
                        )
                    ),
                    0,
                )
            ).where(CreditTransactionModel.workspace_id == workspace_id)
        )
        return int(result.scalar_one())


def _to_transaction(row: CreditTransactionModel) -> CreditTransaction:
    return CreditTransaction(
        id=row.id,
        workspace_id=row.workspace_id,
        reason=CreditReason(row.reason),
        amount_cents=row.amount_cents,
        balance_after_cents=row.balance_after_cents,
        description=row.description,
        source_ref=row.source_ref,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


class SqlCouponRepository:
    """Implements `domain.ports.CouponRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_code(self, code: str) -> Coupon | None:
        # Normalized on the way in as well as on the way to storage, so
        # the unique index *is* the case-insensitive uniqueness rule
        # rather than something every lookup has to remember.
        result = await self._session.execute(
            select(CouponModel).where(CouponModel.code == normalize_code(code))
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_coupon(row)

    async def has_redeemed(self, *, coupon_id: str, workspace_id: str) -> bool:
        result = await self._session.execute(
            select(CouponRedemptionModel.id).where(
                CouponRedemptionModel.coupon_id == coupon_id,
                CouponRedemptionModel.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def record_redemption(
        self,
        *,
        coupon_id: str,
        workspace_id: str,
        credited_cents: int,
        redeemed_by_user_id: str | None,
    ) -> None:
        self._session.add(
            CouponRedemptionModel(
                id=str(uuid.uuid4()),
                coupon_id=coupon_id,
                workspace_id=workspace_id,
                credited_cents=credited_cents,
                redeemed_by_user_id=redeemed_by_user_id,
            )
        )
        # Incremented in SQL rather than read-modify-written: two
        # concurrent redemptions of a limited coupon would otherwise both
        # read the same count and the limit would be exceeded.
        await self._session.execute(
            update(CouponModel)
            .where(CouponModel.id == coupon_id)
            .values(redemption_count=CouponModel.redemption_count + 1)
        )
        await self._session.flush()


def _to_coupon(row: CouponModel) -> Coupon:
    return Coupon(
        id=row.id,
        code=row.code,
        kind=DiscountKind(row.kind),
        value=row.value,
        description=row.description,
        is_active=row.is_active,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        max_redemptions=row.max_redemptions,
        redemption_count=row.redemption_count,
        eligible_plan_slugs=frozenset(row.eligible_plan_slugs or []),
        credit_expires_after_days=row.credit_expires_after_days,
        created_at=row.created_at,
    )


class SqlReferralRepository:
    """Implements `domain.ports.ReferralRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, referrer_workspace_id: str, referred_workspace_id: str, code: str
    ) -> Referral:
        referral = ReferralModel(
            id=str(uuid.uuid4()),
            referrer_workspace_id=referrer_workspace_id,
            referred_workspace_id=referred_workspace_id,
            code=code,
            status=ReferralStatus.PENDING.value,
        )
        self._session.add(referral)
        await self._session.flush()
        return _to_referral(referral)

    async def get_for_referred(self, referred_workspace_id: str) -> Referral | None:
        result = await self._session.execute(
            select(ReferralModel).where(
                ReferralModel.referred_workspace_id == referred_workspace_id
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_referral(row)

    async def list_for_referrer(self, *, referrer_workspace_id: str, limit: int) -> list[Referral]:
        result = await self._session.execute(
            select(ReferralModel)
            .where(ReferralModel.referrer_workspace_id == referrer_workspace_id)
            .order_by(ReferralModel.created_at.desc())
            .limit(limit)
        )
        return [_to_referral(row) for row in result.scalars().all()]

    async def transition(
        self,
        *,
        referral_id: str,
        status: ReferralStatus,
        referrer_reward_cents: int | None = None,
        referred_reward_cents: int | None = None,
        voided_reason: str | None = None,
    ) -> Referral:
        result = await self._session.execute(
            select(ReferralModel).where(ReferralModel.id == referral_id)
        )
        row = result.scalar_one()
        row.status = status.value
        if referrer_reward_cents is not None:
            row.referrer_reward_cents = referrer_reward_cents
        if referred_reward_cents is not None:
            row.referred_reward_cents = referred_reward_cents
        if voided_reason is not None:
            row.voided_reason = voided_reason
        if status is ReferralStatus.QUALIFIED:
            row.qualified_at = datetime.now(row.created_at.tzinfo)
        if status is ReferralStatus.REWARDED:
            row.rewarded_at = datetime.now(row.created_at.tzinfo)
        await self._session.flush()
        return _to_referral(row)


def _to_referral(row: ReferralModel) -> Referral:
    return Referral(
        id=row.id,
        referrer_workspace_id=row.referrer_workspace_id,
        referred_workspace_id=row.referred_workspace_id,
        code=row.code,
        status=ReferralStatus(row.status),
        referrer_reward_cents=row.referrer_reward_cents,
        referred_reward_cents=row.referred_reward_cents,
        qualified_at=row.qualified_at,
        rewarded_at=row.rewarded_at,
        voided_reason=row.voided_reason,
        created_at=row.created_at,
    )
