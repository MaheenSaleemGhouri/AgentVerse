import { Download, Gift, Share2, UserPlus } from "lucide-react";

import type { ReferralSummary } from "@/lib/api/billing";
import type { GrowthMetrics } from "@/lib/api/growth";

import { StatCard } from "@/components/patterns/stat-card";

/**
 * Referral and marketplace growth-funnel counts (Phase 11). Every card
 * is sourced from a live endpoint — `/billing/referrals` (existing) and
 * `/growth/metrics` (new) — never an invented number.
 */
export function GrowthSection({
  referrals,
  growthMetrics,
}: {
  referrals: ReferralSummary;
  growthMetrics: GrowthMetrics;
}): React.JSX.Element {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium text-muted-foreground">Growth — referrals & marketplace</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Referral code"
          value={referrals.code}
          hint={`${referrals.pending} pending`}
          icon={UserPlus}
        />
        <StatCard
          label="Rewarded referrals"
          value={referrals.rewarded}
          hint={`$${(referrals.total_earned_cents / 100).toFixed(2)} earned`}
          icon={Gift}
        />
        <StatCard
          label="Marketplace shares"
          value={growthMetrics.marketplace_shares}
          hint="Share links generated"
          icon={Share2}
        />
        <StatCard
          label="Listing installs"
          value={growthMetrics.marketplace_installs}
          hint="Across this workspace's listings"
          icon={Download}
        />
      </div>
    </section>
  );
}
