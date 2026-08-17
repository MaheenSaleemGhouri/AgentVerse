"""Response schema for `GET /{workspace_id}/growth/metrics` (Phase 11)."""

from __future__ import annotations

from pydantic import BaseModel


class GrowthMetricsResponse(BaseModel):
    referral_code: str
    referrals_pending: int
    referrals_qualified: int
    referrals_rewarded: int
    referral_earnings_cents: int
    marketplace_shares: int
    marketplace_installs: int
