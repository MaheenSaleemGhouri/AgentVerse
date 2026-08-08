import * as React from "react";

import type { EntitlementLine, Plan } from "@/lib/api/billing";

import { UsageMeter } from "@/components/billing/usage-meter";
import { Card } from "@/components/ui/card";

/** Dimensions worth surfacing on the dashboard, in the order the
 * reference's usage panel implies: the thing you run, what it costs in
 * tokens, and the tools it reached for. Storage and bandwidth stay on
 * the billing page, where someone is actually looking at them. */
const HEADLINE = ["agent_runs", "tokens", "mcp_calls"] as const;

/**
 * This period's consumption against the plan's allowances.
 *
 * The approved reference shows a line chart of executions over months.
 * There is no endpoint that returns a monthly series — `agent_runs` is
 * metered against the *current* billing period only — so this panel
 * shows what the data actually supports: real usage against a real
 * limit. Drawing six invented months would have matched the picture and
 * lied about the product.
 *
 * `UsageMeter` is reused wholesale from the billing surface rather than
 * reimplemented: it already handles unlimited plans (no bar, because a
 * bar with no maximum has nothing truthful to draw), the at-limit and
 * approaching-limit states, and the rule that none of those are
 * signalled by colour alone.
 */
export function UsageOverview({
  metered,
  plan,
}: {
  metered: EntitlementLine[];
  plan: Plan;
}): React.JSX.Element {
  const lines = HEADLINE.map((dimension) =>
    metered.find((line) => line.dimension === dimension)
  ).filter((line): line is EntitlementLine => line !== undefined);

  return (
    <Card className="gap-5 p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base font-semibold tracking-tight">Usage this period</h2>
        <span className="text-xs text-muted-foreground">{plan.display_name} plan</span>
      </div>

      {lines.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing metered yet this period. Usage appears here once agents start running.
        </p>
      ) : (
        <div className="space-y-4">
          {lines.map((line) => (
            <UsageMeter key={line.dimension} line={line} />
          ))}
        </div>
      )}
    </Card>
  );
}
