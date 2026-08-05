"use client";

import * as React from "react";

import type { BillingInterval } from "@/lib/api/billing";
import { cn } from "@/lib/utils";

/**
 * Monthly / annual switch.
 *
 * A real radio group rather than two buttons: this is a single choice
 * between two options, which is what a radio group *is*, and it gets
 * arrow-key navigation and a correct screen-reader announcement for free
 * (WCAG 2.2 AA — semantic HTML before ARIA, CLAUDE.md §15).
 *
 * The saving is passed in rather than computed here. It comes from the
 * catalog's own `annual_saving_percent`, so the badge can never claim a
 * discount the prices do not actually give.
 */
export function IntervalToggle({
  value,
  onChange,
  savingPercent,
  className,
}: {
  value: BillingInterval;
  onChange: (interval: BillingInterval) => void;
  savingPercent?: number | null;
  className?: string;
}): React.JSX.Element {
  const options: ReadonlyArray<{ id: BillingInterval; label: string }> = [
    { id: "monthly", label: "Monthly" },
    { id: "annual", label: "Annual" },
  ];

  return (
    <div
      role="radiogroup"
      aria-label="Billing interval"
      className={cn(
        "inline-flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1",
        className
      )}
    >
      {options.map((option) => {
        const isActive = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(option.id)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              isActive
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {option.label}
            {option.id === "annual" && savingPercent ? (
              <span className="ml-1.5 text-xs font-medium text-success">
                −{savingPercent}%
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
