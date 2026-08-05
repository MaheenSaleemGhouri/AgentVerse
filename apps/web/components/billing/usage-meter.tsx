"use client";

import { AlertTriangle } from "lucide-react";
import * as React from "react";

import { Progress } from "@/components/ui/progress";
import type { EntitlementLine } from "@/lib/api/billing";
import { formatNumber, humanizeDimension } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * One dimension's consumption against its allowance.
 *
 * Three states, each rendered differently on purpose:
 *
 * - **Unlimited** (`limit === null`) shows the count and no bar. A
 *   progress bar with no maximum has nothing truthful to draw, and
 *   rendering one at some arbitrary fill would be a fabricated number.
 * - **At or over the limit** is called out with an icon and a label, not
 *   only with colour — WCAG 2.2 AA, and CLAUDE.md §15's "status is never
 *   colour-only".
 * - **Approaching** (the backend's 80% threshold) gets a warning tint, so
 *   the nudge comes from the server's own rule rather than a second
 *   threshold invented in the UI.
 */
export function UsageMeter({
  line,
  className,
}: {
  line: EntitlementLine;
  className?: string;
}): React.JSX.Element {
  const label = humanizeDimension(line.dimension);
  const isUnlimited = line.limit === null;
  const percent = line.percent_used ?? 0;

  const tone = line.at_limit
    ? "text-destructive"
    : line.approaching_limit
      ? "text-warning"
      : "text-muted-foreground";

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-foreground">{label}</span>
        <span className={cn("text-xs tabular-nums", tone)}>
          {isUnlimited ? (
            <>{formatNumber(line.used)} used · Unlimited</>
          ) : (
            <>
              {formatNumber(line.used)} / {formatNumber(line.limit ?? 0)}
            </>
          )}
        </span>
      </div>

      {isUnlimited ? (
        // A deliberate absence rather than a full or empty bar.
        <p className="text-xs text-muted-foreground">No limit on this plan</p>
      ) : (
        <Progress
          value={percent}
          aria-label={`${label}: ${formatNumber(line.used)} of ${formatNumber(line.limit ?? 0)} used`}
          className={cn(
            line.at_limit && "[&>[data-slot=progress-indicator]]:bg-destructive",
            !line.at_limit &&
              line.approaching_limit &&
              "[&>[data-slot=progress-indicator]]:bg-warning"
          )}
        />
      )}

      {line.at_limit && (
        <p className="flex items-center gap-1.5 text-xs font-medium text-destructive">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
          Limit reached — upgrade to continue
        </p>
      )}
      {!line.at_limit && line.approaching_limit && (
        <p className="flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
          {percent}% of your allowance used
        </p>
      )}
    </div>
  );
}
