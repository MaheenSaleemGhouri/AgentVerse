"""`GET /{workspace_id}/growth/metrics` — Phase 11's growth-funnel read
surface: referral performance (already tracked by `billing_service`) plus
marketplace share/install activity, in one call for the Analytics page's
Growth section.

`require_viewer`, same reasoning `billing_service/interface/routes/
credits.py` already states for the referral code: this is workspace
performance data a member can see, not a privileged action.

Composes three bounded contexts' own services (`AuditService`,
`CreditService`, `MarketplaceService`) rather than reading any of their
tables directly — the same cross-context-via-service shape
`auth_service/interface/routes/workspaces.py`'s `create_workspace`
already uses for `CreditService` (CLAUDE.md Rule 5).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.auth_service.interface.dependencies.services import get_audit_service
from agentverse_api.auth_service.interface.schemas.growth import GrowthMetricsResponse
from agentverse_api.billing_service.application.credit_service import CreditService
from agentverse_api.billing_service.domain.referral import ReferralStatus
from agentverse_api.billing_service.interface.dependencies.services import get_credit_service
from agentverse_api.marketplace_service.application.marketplace_service import MarketplaceService
from agentverse_api.marketplace_service.interface.dependencies.services import (
    get_marketplace_service,
)

#: Must match the literal `action` string
#: `marketplace_service/interface/routes/marketplace.py`'s
#: `share_listing_route` writes — not imported across the two route
#: modules (would be a cross-context routes-importing-routes coupling
#: this codebase doesn't otherwise have), so keep them in sync by hand,
#: same as every other `audit.record(action=...)` string literal here.
MARKETPLACE_SHARE_CREATED_ACTION = "marketplace.share_created"

router = APIRouter(prefix="/api/v1/workspaces", tags=["growth"])


@router.get("/{workspace_id}/growth/metrics", response_model=GrowthMetricsResponse)
async def get_growth_metrics_route(
    context: WorkspaceContext = Depends(require_viewer),
    audit: AuditService = Depends(get_audit_service),
    credits: CreditService = Depends(get_credit_service),
    marketplace: MarketplaceService = Depends(get_marketplace_service),
) -> GrowthMetricsResponse:
    referrals = await credits.list_referrals(workspace_id=context.workspace_id)
    referral_counts = {status: 0 for status in ReferralStatus}
    for referral in referrals:
        referral_counts[referral.status] += 1

    action_counts = await audit.counts_for_actions(
        workspace_id=context.workspace_id, actions=[MARKETPLACE_SHARE_CREATED_ACTION]
    )
    listings = await marketplace.list_mine(publisher_workspace_id=context.workspace_id)

    return GrowthMetricsResponse(
        referral_code=await credits.ensure_code(context.workspace_id),
        referrals_pending=referral_counts[ReferralStatus.PENDING],
        referrals_qualified=referral_counts[ReferralStatus.QUALIFIED],
        referrals_rewarded=referral_counts[ReferralStatus.REWARDED],
        referral_earnings_cents=sum(
            r.referrer_reward_cents for r in referrals if r.status is ReferralStatus.REWARDED
        ),
        marketplace_shares=action_counts[MARKETPLACE_SHARE_CREATED_ACTION],
        marketplace_installs=sum(listing.install_count for listing in listings),
    )
