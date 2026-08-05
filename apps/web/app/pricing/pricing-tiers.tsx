"use client";

import Link from "next/link";
import * as React from "react";

import { IntervalToggle } from "@/components/billing/interval-toggle";
import { PlanCard } from "@/components/billing/plan-card";
import { Button } from "@/components/ui/button";
import type { BillingInterval, Plan } from "@/lib/api/billing";

/**
 * The interactive half of the pricing page.
 *
 * Only the interval toggle needs state, so only this piece is a Client
 * Component; the page around it stays server-rendered and cacheable
 * (CLAUDE.md §6: every `'use client'` boundary is minimal and justified).
 *
 * The plans arrive as props from the server fetch rather than being
 * re-fetched here — the catalog is the same for every visitor, and a
 * client fetch would turn a cacheable static page into one round trip
 * per visitor for data that never varies by user.
 */
export function PricingTiers({ plans }: { plans: Plan[] }): React.JSX.Element {
  const [interval, setInterval] = React.useState<BillingInterval>("monthly");

  // The headline saving comes from whichever plan actually offers the
  // largest one, read off the catalog. Hardcoding "save 20%" here would
  // be a claim the prices might not support.
  const bestSaving = React.useMemo(
    () =>
      plans.reduce<number | null>((best, plan) => {
        const saving = plan.annual_saving_percent;
        if (saving === null || saving === undefined) return best;
        return best === null || saving > best ? saving : best;
      }, null),
    [plans]
  );

  // Team is the recommended tier: it is the one the packaging is built
  // around, and marking none would leave the eye with no entry point.
  const recommendedSlug = "team";

  return (
    <div className="space-y-8">
      <div className="flex justify-center">
        <IntervalToggle
          value={interval}
          onChange={setInterval}
          savingPercent={bestSaving}
        />
      </div>

      <div className="grid grid-cols-1 items-stretch gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {plans.map((plan) => {
          const isCustomPriced =
            plan.monthly_price_cents === null && plan.annual_price_cents === null;
          return (
            <PlanCard
              key={plan.id}
              plan={plan}
              interval={interval}
              isRecommended={plan.slug === recommendedSlug}
              action={
                isCustomPriced ? (
                  <Button variant="outline" className="w-full" asChild>
                    <a href="mailto:sales@agentverse.dev?subject=Enterprise%20plan">
                      Contact sales
                    </a>
                  </Button>
                ) : (
                  // Signup, not checkout: a visitor with no workspace has
                  // nothing to attach a subscription to, and sending them
                  // into a payment flow first would collect a card for an
                  // account that does not exist.
                  <Button
                    variant={plan.slug === recommendedSlug ? "default" : "outline"}
                    className="w-full"
                    asChild
                  >
                    <Link href={`/signup?plan=${plan.slug}`}>
                      {plan.monthly_price_cents === 0 ? "Start free" : "Start free trial"}
                    </Link>
                  </Button>
                )
              }
            />
          );
        })}
      </div>
    </div>
  );
}
