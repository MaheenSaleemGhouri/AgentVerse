"use client";

import { CalendarClock, CreditCard, ExternalLink, TriangleAlert } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { Plan, Subscription } from "@/lib/api/billing";
import { formatCents, formatDate } from "@/lib/format";

/**
 * What this workspace is on right now, and what happens next.
 *
 * The states are deliberately distinct rather than collapsed into one
 * status line, because each needs a different next action:
 *
 * - **No subscription** is not an error — the workspace is genuinely on
 *   Free and operating as intended.
 * - **Scheduled to cancel** still reads as active, because it *is*: the
 *   customer paid for this period. It shows the end date and an undo.
 * - **Past due** shows the dunning deadline, not a vague warning. A
 *   customer who knows the date can act; one told "payment issue" cannot.
 */

const STATUS_LABELS: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  trialing: { label: "Trial", variant: "secondary" },
  active: { label: "Active", variant: "default" },
  past_due: { label: "Payment failed", variant: "destructive" },
  paused: { label: "Paused", variant: "outline" },
  canceled: { label: "Canceled", variant: "outline" },
};

export function SubscriptionCard({
  subscription,
  plan,
  onManage,
  onCancel,
  onResume,
  onUpgrade,
  isBusy,
  canManage,
  providerConfigured,
}: {
  subscription: Subscription | null;
  plan: Plan | null;
  onManage?: () => void;
  onCancel?: () => void;
  onResume?: () => void;
  onUpgrade?: () => void;
  isBusy?: boolean;
  canManage: boolean;
  providerConfigured: boolean;
}): React.JSX.Element {
  if (subscription === null) {
    return (
      <Card className="gap-4 p-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h2 className="font-medium">{plan?.display_name ?? "Free"} plan</h2>
            <Badge variant="secondary">Current plan</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {plan?.description ??
              "This workspace has no subscription. It is on the Free plan."}
          </p>
        </div>
        {canManage && onUpgrade && (
          <div>
            <Button onClick={onUpgrade} disabled={isBusy || !providerConfigured}>
              <CreditCard className="size-4" aria-hidden="true" />
              Choose a plan
            </Button>
            {!providerConfigured && (
              <p className="mt-2 text-xs text-muted-foreground">
                Payments are not configured in this environment.
              </p>
            )}
          </div>
        )}
      </Card>
    );
  }

  const status = STATUS_LABELS[subscription.status] ?? {
    label: subscription.status,
    variant: "outline" as const,
  };

  return (
    <Card className="gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-medium">{plan?.display_name ?? subscription.plan_slug} plan</h2>
            <Badge variant={status.variant}>{status.label}</Badge>
            {subscription.cancel_at_period_end && (
              <Badge variant="outline">Cancels {formatDate(subscription.current_period_end)}</Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Billed {subscription.billing_interval}
            {plan &&
              (subscription.billing_interval === "annual"
                ? plan.annual_price_cents !== null &&
                  ` · ${formatCents(plan.annual_price_cents, plan.currency)} per year`
                : plan.monthly_price_cents !== null &&
                  ` · ${formatCents(plan.monthly_price_cents, plan.currency)} per month`)}
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-1 gap-4 border-t border-border pt-4 sm:grid-cols-2">
        <div className="space-y-0.5">
          <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <CalendarClock className="size-3.5" aria-hidden="true" />
            Current period
          </dt>
          <dd className="text-sm tabular-nums">
            {formatDate(subscription.current_period_start)} –{" "}
            {formatDate(subscription.current_period_end)}
          </dd>
        </div>
        {subscription.trial_end && (
          <div className="space-y-0.5">
            <dt className="text-xs text-muted-foreground">Trial ends</dt>
            <dd className="text-sm tabular-nums">{formatDate(subscription.trial_end)}</dd>
          </div>
        )}
      </dl>

      {subscription.dunning && (
        // The date, not a vague warning: a customer who knows when
        // service stops can act, one told "payment issue" cannot.
        <div
          role="alert"
          className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive-soft p-4"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
          <div className="space-y-1 text-sm">
            <p className="font-medium text-foreground">
              We could not take your last payment
            </p>
            <p className="text-muted-foreground">
              Your subscription stays active until{" "}
              <span className="font-medium text-foreground">
                {formatDate(subscription.dunning.deadline)}
              </span>{" "}
              ({subscription.dunning.days_remaining} days). Update your payment
              method to keep it running.
            </p>
          </div>
        </div>
      )}

      {canManage && (
        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          {onManage && (
            <Button variant="outline" onClick={onManage} disabled={isBusy || !providerConfigured}>
              <ExternalLink className="size-4" aria-hidden="true" />
              Manage payment &amp; invoices
            </Button>
          )}
          {onUpgrade && (
            <Button variant="outline" onClick={onUpgrade} disabled={isBusy}>
              Change plan
            </Button>
          )}
          {subscription.cancel_at_period_end
            ? onResume && (
                <Button variant="outline" onClick={onResume} disabled={isBusy}>
                  Keep my subscription
                </Button>
              )
            : onCancel && (
                <Button variant="ghost" onClick={onCancel} disabled={isBusy}>
                  Cancel subscription
                </Button>
              )}
        </div>
      )}
      {canManage && !providerConfigured && (
        <p className="text-xs text-muted-foreground">
          Payments are not configured in this environment, so the provider-hosted
          actions are unavailable.
        </p>
      )}
    </Card>
  );
}
