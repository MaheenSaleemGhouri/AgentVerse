"use client";

import { Check, Sparkles } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { BillingInterval, Plan } from "@/lib/api/billing";
import { formatCents, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * One tier, priced from the live catalog.
 *
 * Every number here comes from `GET /api/v1/plans` — the same rows
 * server-side enforcement reads (ADR-0012). There is no hardcoded price
 * anywhere in this component, which is what keeps the pricing page and
 * the quota a customer actually hits from ever disagreeing.
 *
 * A custom-priced tier renders "Contact sales" rather than a number:
 * `monthly_price_cents` is genuinely null for Enterprise, and rendering
 * "$0" would be a commitment the product has not made.
 */

/**
 * Capabilities worth listing on a card, in the order a buyer reads them.
 *
 * A subset on purpose: the catalog carries sixteen, and a card listing
 * all of them stops being scannable. The rest are visible on the plan
 * comparison in Billing, so nothing is hidden — this is editorial
 * ordering, not a second source of truth.
 */
const HEADLINE_CAPABILITIES: ReadonlyArray<{ key: string; label: string }> = [
  { key: "multi_agent", label: "Multi-agent teams" },
  { key: "team_collaboration", label: "Shared workspaces" },
  { key: "analytics", label: "Analytics" },
  { key: "priority_queue", label: "Priority run queue" },
  { key: "sso", label: "SSO" },
  { key: "audit_log_export", label: "Audit log export" },
  { key: "custom_roles", label: "Custom roles" },
  { key: "sla", label: "SLA" },
];

/** The limits a buyer compares first, labelled for a pricing card. */
const HEADLINE_LIMITS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "agents", label: "agents" },
  { key: "seats", label: "seats" },
  { key: "knowledge_bases", label: "knowledge bases" },
];

function limitLabel(value: number | null | undefined, noun: string): string {
  // `null` means unlimited throughout this system — never a sentinel, so
  // it is safe to branch on directly.
  return value === null || value === undefined
    ? `Unlimited ${noun}`
    : `${formatNumber(value)} ${noun}`;
}

export function PlanCard({
  plan,
  interval,
  isCurrent,
  isRecommended,
  action,
  className,
}: {
  plan: Plan;
  interval: BillingInterval;
  isCurrent?: boolean;
  isRecommended?: boolean;
  action?: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  const price =
    interval === "annual" ? plan.annual_price_cents : plan.monthly_price_cents;
  const isCustomPriced = plan.monthly_price_cents === null && plan.annual_price_cents === null;
  const limits = plan.resource_limits as Record<string, number | null> | undefined;
  const capabilities = new Set(plan.capabilities ?? []);

  return (
    <Card
      className={cn(
        "relative gap-4 p-6",
        // The recommended tier is lifted by a border, not a gradient or a
        // scale transform — AVDS restraint, and a scaled card breaks the
        // grid's baseline alignment on tablet.
        isRecommended && "border-primary/60 shadow-md",
        className
      )}
    >
      {isRecommended && (
        <Badge className="absolute -top-2.5 left-6 gap-1" variant="default">
          <Sparkles className="size-3" aria-hidden="true" />
          Most popular
        </Badge>
      )}

      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <h3 className="font-medium">{plan.display_name}</h3>
          {isCurrent && (
            <Badge variant="secondary" className="text-xs">
              Current plan
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{plan.description}</p>
      </div>

      <div className="min-h-14">
        {isCustomPriced ? (
          <p className="text-2xl font-semibold tracking-tight">Contact sales</p>
        ) : (
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-semibold tracking-tight tabular-nums">
              {formatCents(price ?? 0, plan.currency)}
            </span>
            <span className="text-sm text-muted-foreground">
              /{interval === "annual" ? "year" : "month"}
            </span>
          </div>
        )}
        {interval === "annual" && plan.annual_saving_percent !== null && (
          <p className="mt-1 text-xs font-medium text-success">
            Save {plan.annual_saving_percent}% versus monthly
          </p>
        )}
        {plan.trial_days > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            {plan.trial_days}-day free trial
          </p>
        )}
      </div>

      <ul className="space-y-2 text-sm">
        {HEADLINE_LIMITS.map(({ key, label }) => (
          <li key={key} className="flex gap-2 text-muted-foreground">
            <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />
            {limitLabel(limits?.[key], label)}
          </li>
        ))}
        {HEADLINE_CAPABILITIES.filter(({ key }) => capabilities.has(key)).map(
          ({ key, label }) => (
            <li key={key} className="flex gap-2 text-muted-foreground">
              <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />
              {label}
            </li>
          )
        )}
      </ul>

      <div className="mt-auto pt-2">
        {action ?? (
          <Button variant={isRecommended ? "default" : "outline"} className="w-full" disabled>
            {isCurrent ? "Current plan" : "Sign in to subscribe"}
          </Button>
        )}
      </div>
    </Card>
  );
}
