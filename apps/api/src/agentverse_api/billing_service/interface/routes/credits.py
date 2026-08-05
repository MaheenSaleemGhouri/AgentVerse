"""Credits, coupon redemption and the referral surface.

**Gating splits by what the action does.** Reading a balance or a
referral code is `require_viewer` — a member seeing that the workspace
holds $20 of credit is not privileged, and the referral code is meant to
be shared. Redeeming a coupon changes what the workspace will be charged,
so it is `require_admin`, same as every other money-moving route.

`workspace_id` comes from the authenticated context in every handler,
never from the path parameter (Rule 6, Rule 11).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_viewer,
)
from agentverse_api.billing_service.application.credit_service import CreditService
from agentverse_api.billing_service.domain.coupon import CouponRejectedError
from agentverse_api.billing_service.domain.credit import is_credit
from agentverse_api.billing_service.interface.dependencies.services import get_credit_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["billing-credits"])


class CreditTransactionResponse(BaseModel):
    id: str
    reason: str
    #: Always positive; `direction` says which way it moved. A signed
    #: amount would make the client responsible for reading the sign
    #: correctly to render a statement.
    amount_cents: int
    direction: str
    balance_after_cents: int
    description: str
    expires_at: datetime | None
    created_at: datetime


class CreditBalanceResponse(BaseModel):
    workspace_id: str
    balance_cents: int
    currency: str
    transactions: list[CreditTransactionResponse]


class RedeemCouponRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class RedeemCouponResponse(BaseModel):
    code: str
    credited_cents: int
    balance_cents: int


class ReferralResponse(BaseModel):
    id: str
    referred_workspace_id: str
    status: str
    referrer_reward_cents: int
    qualified_at: datetime | None
    rewarded_at: datetime | None
    created_at: datetime


class ReferralSummaryResponse(BaseModel):
    """The referral panel's whole payload.

    `pending` is reported alongside `rewarded` deliberately: the ratio
    between them is the loop efficiency `growth-engineer` judges the
    programme by, and showing only successes would make a loop that never
    converts look perfect.
    """

    code: str
    pending: int
    qualified: int
    rewarded: int
    total_earned_cents: int
    referrals: list[ReferralResponse]


@router.get("/{workspace_id}/billing/credits", response_model=CreditBalanceResponse)
async def get_credits_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: CreditService = Depends(get_credit_service),
) -> CreditBalanceResponse:
    """Balance plus the ledger behind it.

    Returned together because a balance on its own is a number nobody can
    explain, and "why is this $40 and not $50" is the first question
    anyone asks about credit.
    """
    balance = await service.balance(context.workspace_id)
    transactions = await service.history(workspace_id=context.workspace_id)
    return CreditBalanceResponse(
        workspace_id=context.workspace_id,
        balance_cents=balance,
        currency="usd",
        transactions=[
            CreditTransactionResponse(
                id=transaction.id,
                reason=transaction.reason.value,
                amount_cents=transaction.amount_cents,
                direction="credit" if is_credit(transaction.reason) else "debit",
                balance_after_cents=transaction.balance_after_cents,
                description=transaction.description,
                expires_at=transaction.expires_at,
                created_at=transaction.created_at,
            )
            for transaction in transactions
        ],
    )


@router.post(
    "/{workspace_id}/billing/credits/redeem",
    response_model=RedeemCouponResponse,
    status_code=status.HTTP_201_CREATED,
)
async def redeem_coupon_route(
    body: RedeemCouponRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: CreditService = Depends(get_credit_service),
) -> RedeemCouponResponse:
    """Redeem a coupon code for account credit.

    A rejection returns the specific reason rather than a generic
    "invalid code": "this has expired" and "you have already used this"
    need different next steps from the customer, and collapsing them
    makes both unactionable.
    """
    try:
        result = await service.redeem_coupon(
            workspace_id=context.workspace_id,
            code=body.code,
            redeemed_by_user_id=context.user_id,
        )
    except CouponRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.rejection.value, "message": str(exc)},
        ) from exc
    return RedeemCouponResponse(
        code=result.code,
        credited_cents=result.credited_cents,
        balance_cents=result.balance_cents,
    )


@router.get("/{workspace_id}/billing/referrals", response_model=ReferralSummaryResponse)
async def get_referrals_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: CreditService = Depends(get_credit_service),
) -> ReferralSummaryResponse:
    """This workspace's referral code and what it has produced.

    The code is derived from the workspace id rather than stored, so it
    is the same every time it is displayed and needs no table of its own.
    """
    referrals = await service.list_referrals(workspace_id=context.workspace_id)
    counts = {"pending": 0, "qualified": 0, "rewarded": 0, "voided": 0}
    for referral in referrals:
        counts[referral.status.value] += 1
    return ReferralSummaryResponse(
        code=service.code_for(context.workspace_id),
        pending=counts["pending"],
        qualified=counts["qualified"],
        rewarded=counts["rewarded"],
        # Only rewarded referrals have actually paid. Counting qualified
        # ones would show the customer money they have not received.
        total_earned_cents=sum(
            referral.referrer_reward_cents
            for referral in referrals
            if referral.status.value == "rewarded"
        ),
        referrals=[
            ReferralResponse(
                id=referral.id,
                referred_workspace_id=referral.referred_workspace_id,
                status=referral.status.value,
                referrer_reward_cents=referral.referrer_reward_cents,
                qualified_at=referral.qualified_at,
                rewarded_at=referral.rewarded_at,
                created_at=referral.created_at,
            )
            for referral in referrals
        ],
    )
