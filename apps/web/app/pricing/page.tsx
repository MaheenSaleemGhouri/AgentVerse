import type { Metadata } from "next";
import Link from "next/link";
import * as React from "react";

import { PricingTiers } from "@/app/pricing/pricing-tiers";
import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { listPublicPlans } from "@/lib/api/billing";
import { formatNumber, humanizeDimension } from "@/lib/format";

/**
 * The public pricing page.
 *
 * Server-rendered and unauthenticated: it is a marketing surface that
 * must be indexable and fast, and it has no per-visitor content
 * (CLAUDE.md §6 — public pages are cached and SEO-optimised, authenticated
 * ones never are). See the `revalidate` note below for what is and is
 * not actually cached today.
 *
 * Every price, limit, capability and overage rate is read from the live
 * `plans` catalog — the same rows server-side quota enforcement reads
 * (ADR-0012). Nothing on this page is a hardcoded number, which is what
 * makes "the price shown" and "the limit actually enforced" incapable of
 * disagreeing.
 */
export const metadata: Metadata = {
  title: "Pricing · AgentVerse",
  description:
    "Simple, published pricing for AgentVerse — build, run and observe AI agents. Free, Pro, Team and Enterprise plans with transparent usage overage rates.",
};

// Public pages are cached (§6). One minute: a price change is an UPDATE
// against `plans`, not a deploy, so a long TTL would keep serving a
// price the product no longer sells.
//
// Known limitation, stated rather than glossed: the *page* still renders
// dynamically, because the root layout fetches SSO providers per request
// and that opts every route out of static generation (`/login` is
// affected the same way). This directive does still cache the catalog
// fetch itself, so the database is hit at most once a minute — but the
// CDN-cacheable static render this page wants needs that layout fetch
// moved behind its own boundary, which is a change to a shared surface
// and out of this milestone's scope.
export const revalidate = 60;

export default async function PricingPage(): Promise<React.JSX.Element> {
  let plans;
  try {
    plans = await listPublicPlans();
  } catch {
    // The catalog is the whole page. A generic 500 would tell a
    // prospective customer nothing; naming the surface and offering a
    // way forward is the §6 error-state contract.
    return (
      <main className="mx-auto w-full max-w-2xl px-6 py-24">
        <ErrorState
          title="Pricing is temporarily unavailable"
          description="We could not load the plan catalog. Please try again shortly, or contact sales@agentverse.dev and we will send it over."
        />
      </main>
    );
  }

  // Overage rates are shown in full: `saas-pricing-expert` requires the
  // exact per-unit rates to be published, not merely "usage-based
  // pricing available". Taken from the highest tier that actually
  // charges overage, which is the rate most customers reach.
  const overagePlan = [...plans]
    .reverse()
    .find((plan) => (plan.overage_rates?.length ?? 0) > 0);

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-16 sm:py-24">
      <header className="mx-auto max-w-2xl space-y-4 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          Pricing that scales with your agents
        </h1>
        <p className="text-lg text-muted-foreground">
          Start free. Pay for what you run. Every limit below is the limit the
          platform actually enforces — no asterisks.
        </p>
      </header>

      <div className="mt-12">
        <PricingTiers plans={plans} />
      </div>

      {overagePlan && (
        <section className="mt-16 space-y-4" aria-labelledby="overage-heading">
          <div className="space-y-1 text-center">
            <h2 id="overage-heading" className="text-xl font-semibold tracking-tight">
              Usage beyond your plan
            </h2>
            <p className="text-sm text-muted-foreground">
              Published rates, billed only past your included allowance. Free
              workspaces are never charged overage — they stop at the limit.
            </p>
          </div>
          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-125 text-sm">
              <caption className="sr-only">
                Usage overage rates on the {overagePlan.display_name} plan
              </caption>
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th scope="col" className="px-5 py-3 font-medium">
                    Dimension
                  </th>
                  <th scope="col" className="px-5 py-3 font-medium">
                    Included
                  </th>
                  <th scope="col" className="px-5 py-3 font-medium">
                    Then
                  </th>
                </tr>
              </thead>
              <tbody>
                {(overagePlan.overage_rates ?? []).map((rate) => {
                  const allowance = (
                    overagePlan.metered_allowances as Record<string, number | null>
                  )?.[rate.dimension];
                  return (
                    <tr key={rate.dimension} className="border-b border-border last:border-0">
                      <th scope="row" className="px-5 py-3 text-left font-normal">
                        {humanizeDimension(rate.dimension)}
                      </th>
                      <td className="px-5 py-3 tabular-nums text-muted-foreground">
                        {allowance === null || allowance === undefined
                          ? "Unlimited"
                          : formatNumber(allowance)}
                      </td>
                      <td className="px-5 py-3 tabular-nums text-muted-foreground">
                        ${(rate.price_cents_per_increment / 100).toFixed(2)} per{" "}
                        {formatNumber(rate.billing_increment)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </section>
      )}

      <section className="mt-16 flex flex-col items-center gap-3 text-center">
        <h2 className="text-xl font-semibold tracking-tight">
          Not sure which plan fits?
        </h2>
        <p className="max-w-lg text-sm text-muted-foreground">
          Every paid plan includes a free trial, and you can change plans at any
          time — we prorate to the second, and show you the exact amount before
          you confirm.
        </p>
        <Button asChild className="mt-2">
          <Link href="/signup">Create a free workspace</Link>
        </Button>
      </section>
    </main>
  );
}
