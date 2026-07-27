import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import * as React from "react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * A single dashboard metric.
 *
 * `delta` is optional deliberately: a stat with no honest comparison
 * period renders no arrow rather than an invented one. Trend indicators
 * are only shown where the data genuinely supports them.
 */
export function StatCard({
  label,
  value,
  hint,
  delta,
  icon: Icon,
  isLoading,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  delta?: { value: string; direction: "up" | "down"; isGood: boolean };
  icon?: React.ComponentType<{ className?: string }>;
  isLoading?: boolean;
}): React.JSX.Element {
  return (
    <Card className="gap-0 p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        {Icon && <Icon className="size-4 text-muted-foreground" aria-hidden="true" />}
      </div>
      {isLoading ? (
        <Skeleton className="mt-3 h-8 w-24" />
      ) : (
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl font-semibold tracking-tight tabular-nums">{value}</span>
          {delta && (
            <span
              className={cn(
                "inline-flex items-center gap-0.5 text-xs font-medium",
                delta.isGood ? "text-success" : "text-destructive"
              )}
            >
              {delta.direction === "up" ? (
                <ArrowUpRight className="size-3" aria-hidden="true" />
              ) : (
                <ArrowDownRight className="size-3" aria-hidden="true" />
              )}
              {delta.value}
            </span>
          )}
        </div>
      )}
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  );
}
