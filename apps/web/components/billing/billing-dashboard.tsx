"use client";

import { Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { CreditsPanel, ReferralPanel } from "@/components/billing/credits-panel";
import { EnterpriseInfrastructurePanel } from "@/components/billing/enterprise-infrastructure-panel";
import { IntervalToggle } from "@/components/billing/interval-toggle";
import { InvoicesPanel, PaymentMethodsPanel } from "@/components/billing/invoices-panel";
import { PlanCard } from "@/components/billing/plan-card";
import { SubscriptionCard } from "@/components/billing/subscription-card";
import { UsageMeter } from "@/components/billing/usage-meter";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  cancelSubscriptionAction,
  changePlanAction,
  createCheckoutSessionAction,
  createPortalSessionAction,
  quotePlanChangeAction,
  redeemCouponAction,
  resumeSubscriptionAction,
} from "@/lib/api/actions";
import type {
  BillingInterval,
  CreditBalance,
  DraftInvoice,
  Entitlements,
  Invoice,
  PaymentMethod,
  Plan,
  PlanChangeQuote,
  PlanTier,
  ReferralSummary,
  Subscription,
} from "@/lib/api/billing";
import { formatCents, formatDate } from "@/lib/format";

/**
 * The billing dashboard.
 *
 * All data arrives as props from the Server Component that fetched it —
 * no client-side initial fetch, so the page is populated on first paint
 * (CLAUDE.md §6). Only the mutations run here, because only they need a
 * client boundary.
 *
 * Tabs rather than one long scroll: the four concerns (plan, usage,
 * invoices, credits) are read at different times by different people,
 * and stacking them would bury the usage meter — the thing a customer
 * opens this page to check — below an invoice table.
 */
export function BillingDashboard({
  workspaceId,
  plans,
  subscription,
  entitlements,
  invoicePreview,
  invoices,
  paymentMethods,
  credits,
  referrals,
  canManage,
}: {
  workspaceId: string;
  plans: Plan[];
  subscription: Subscription | null;
  entitlements: Entitlements;
  invoicePreview: DraftInvoice | null;
  invoices: Invoice[] | null;
  paymentMethods: PaymentMethod[] | null;
  credits: CreditBalance;
  referrals: ReferralSummary;
  canManage: boolean;
}): React.JSX.Element {
  const [isBusy, setIsBusy] = React.useState(false);
  const [showPlans, setShowPlans] = React.useState(false);
  const [interval, setInterval] = React.useState<BillingInterval>(
    (subscription?.billing_interval as BillingInterval | undefined) ?? "monthly"
  );
  const [pendingChange, setPendingChange] = React.useState<{
    plan: Plan;
    quote: PlanChangeQuote;
  } | null>(null);
  const [confirmCancel, setConfirmCancel] = React.useState(false);

  // `null` from either provider-backed read means this environment has no
  // payment provider — a deliberate state, not a failure.
  const providerConfigured = invoices !== null || paymentMethods !== null;

  const currentPlan =
    plans.find((plan) => plan.slug === entitlements.plan.slug) ?? entitlements.plan;

  async function run(action: () => Promise<void>, failure: string): Promise<void> {
    setIsBusy(true);
    try {
      await action();
    } catch {
      toast.error(failure);
    } finally {
      setIsBusy(false);
    }
  }

  async function startCheckout(plan: Plan): Promise<void> {
    await run(async () => {
      const session = await createCheckoutSessionAction(workspaceId, {
        plan_slug: plan.slug as PlanTier,
        interval,
      });
      // A full navigation, not a router push: the destination is the
      // provider's own hosted page, outside this app.
      window.location.assign(session.checkout_url);
    }, "Could not start checkout. Please try again.");
  }

  async function openPortal(): Promise<void> {
    await run(async () => {
      const session = await createPortalSessionAction(workspaceId);
      window.location.assign(session.portal_url);
    }, "Could not open the billing portal. Please try again.");
  }

  async function askToChange(plan: Plan): Promise<void> {
    await run(async () => {
      const quote = await quotePlanChangeAction(workspaceId, {
        plan_slug: plan.slug as PlanTier,
        interval,
      });
      // The customer sees the exact proration before confirming — never
      // discovers it on the invoice.
      setPendingChange({ plan, quote });
    }, "Could not price that plan change.");
  }

  async function confirmChange(): Promise<void> {
    if (!pendingChange) return;
    const target = pendingChange;
    await run(async () => {
      await changePlanAction(
        workspaceId,
        { plan_slug: target.plan.slug as PlanTier, interval },
        // Required by the endpoint. Generated per confirmation so a
        // double-click replays the same key rather than applying a
        // second plan change — each one becomes an invoice line.
        `plan-change:${workspaceId}:${target.plan.slug}:${interval}:${target.quote.proration.net_cents}`
      );
      toast.success(`Switched to ${target.plan.display_name}.`);
      setPendingChange(null);
      setShowPlans(false);
      window.location.reload();
    }, "Could not change the plan.");
  }

  async function cancel(): Promise<void> {
    await run(async () => {
      await cancelSubscriptionAction(workspaceId, { at_period_end: true });
      toast.success("Your subscription will end at the close of this period.");
      setConfirmCancel(false);
      window.location.reload();
    }, "Could not cancel the subscription.");
  }

  async function resume(): Promise<void> {
    await run(async () => {
      await resumeSubscriptionAction(workspaceId);
      toast.success("Your subscription will continue.");
      window.location.reload();
    }, "Could not resume the subscription.");
  }

  async function redeem(code: string): Promise<void> {
    await run(async () => {
      const result = await redeemCouponAction(workspaceId, code);
      toast.success(`${formatCents(result.credited_cents)} credit added.`);
      window.location.reload();
    }, "That code could not be redeemed.");
  }

  return (
    <>
      <Tabs defaultValue="overview" className="gap-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="credits">Credits &amp; referrals</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <SubscriptionCard
            subscription={subscription}
            plan={currentPlan as Plan}
            canManage={canManage}
            providerConfigured={providerConfigured}
            isBusy={isBusy}
            onUpgrade={() => setShowPlans((open) => !open)}
            // Spread rather than pass `undefined`: `exactOptionalPropertyTypes`
            // treats an explicit `undefined` as a different thing from an
            // absent prop, which is the point of the flag.
            {...(subscription
              ? {
                  onManage: openPortal,
                  onCancel: () => setConfirmCancel(true),
                  onResume: resume,
                }
              : {})}
          />

          {showPlans && (
            <section className="space-y-4" aria-label="Available plans">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-medium">Choose a plan</h2>
                <IntervalToggle value={interval} onChange={setInterval} />
              </div>
              <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {plans.map((plan) => {
                  const isCurrent = plan.slug === entitlements.plan.slug;
                  const isCustomPriced =
                    plan.monthly_price_cents === null && plan.annual_price_cents === null;
                  return (
                    <PlanCard
                      key={plan.id}
                      plan={plan}
                      interval={interval}
                      isCurrent={isCurrent}
                      action={
                        isCurrent ? (
                          <Button variant="outline" className="w-full" disabled>
                            Current plan
                          </Button>
                        ) : isCustomPriced ? (
                          <Button variant="outline" className="w-full" asChild>
                            <a href="mailto:sales@agentverse.dev?subject=Enterprise%20plan">
                              Contact sales
                            </a>
                          </Button>
                        ) : (
                          <Button
                            className="w-full"
                            disabled={isBusy || !providerConfigured}
                            onClick={() =>
                              subscription ? askToChange(plan) : startCheckout(plan)
                            }
                          >
                            {isBusy && (
                              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                            )}
                            {subscription ? "Switch to this plan" : "Subscribe"}
                          </Button>
                        )
                      }
                    />
                  );
                })}
              </div>
            </section>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card className="gap-4 p-6">
              <div className="space-y-1">
                <h2 className="font-medium">Usage this period</h2>
                <p className="text-sm text-muted-foreground">
                  Your highest-consumption dimensions. Full detail on the Usage tab.
                </p>
              </div>
              <div className="space-y-4">
                {entitlements.metered.slice(0, 4).map((line) => (
                  <UsageMeter key={line.dimension} line={line} />
                ))}
              </div>
            </Card>

            <CreditsPanel
              credits={credits}
              onRedeem={redeem}
              isRedeeming={isBusy}
              canRedeem={canManage}
            />
          </div>
        </TabsContent>

        <TabsContent value="usage" className="space-y-6">
          <Card className="gap-5 p-6">
            <div className="space-y-1">
              <h2 className="font-medium">Included resources</h2>
              <p className="text-sm text-muted-foreground">
                Standing counts — how many exist right now.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {entitlements.resources.map((line) => (
                <UsageMeter key={line.dimension} line={line} />
              ))}
            </div>
          </Card>

          <Card className="gap-5 p-6">
            <div className="space-y-1">
              <h2 className="font-medium">Metered usage</h2>
              <p className="text-sm text-muted-foreground">
                Consumption this billing period. Resets when the period rolls over.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              {entitlements.metered.map((line) => (
                <UsageMeter key={line.dimension} line={line} />
              ))}
            </div>
          </Card>

          <EnterpriseInfrastructurePanel entitlements={entitlements} />
        </TabsContent>

        <TabsContent value="invoices" className="space-y-6">
          <InvoicesPanel invoices={invoices} preview={invoicePreview} />
          <PaymentMethodsPanel
            methods={paymentMethods}
            canManage={canManage}
            onManage={openPortal}
          />
        </TabsContent>

        <TabsContent value="credits" className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <CreditsPanel
            credits={credits}
            onRedeem={redeem}
            isRedeeming={isBusy}
            canRedeem={canManage}
          />
          <ReferralPanel summary={referrals} currency={credits.currency} />
        </TabsContent>
      </Tabs>

      <AlertDialog
        open={pendingChange !== null}
        onOpenChange={(open) => !open && setPendingChange(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Switch to {pendingChange?.plan.display_name}?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  We prorate to the second. Here is exactly what changes on your
                  next invoice.
                </p>
                {pendingChange && (
                  <dl className="space-y-1.5 rounded-lg border border-border bg-muted/40 p-3 text-sm">
                    <div className="flex justify-between gap-4">
                      <dt>Credit for unused {pendingChange.quote.from_plan} time</dt>
                      <dd className="tabular-nums">
                        −{formatCents(pendingChange.quote.proration.unused_credit_cents)}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt>Prorated {pendingChange.quote.to_plan} charge</dt>
                      <dd className="tabular-nums">
                        {formatCents(pendingChange.quote.proration.prorated_charge_cents)}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-4 border-t border-border pt-1.5 font-medium">
                      <dt>
                        {pendingChange.quote.proration.net_cents >= 0
                          ? "Due now"
                          : "Credited to your account"}
                      </dt>
                      <dd className="tabular-nums">
                        {formatCents(Math.abs(pendingChange.quote.proration.net_cents))}
                      </dd>
                    </div>
                  </dl>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isBusy}>Keep current plan</AlertDialogCancel>
            <AlertDialogAction onClick={confirmChange} disabled={isBusy}>
              Confirm change
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel your subscription?</AlertDialogTitle>
            <AlertDialogDescription>
              {/* Reversible until the period ends, and the copy says so —
                  confirmation friction scales with reversibility (§15). */}
              You keep everything until{" "}
              {subscription ? formatDate(subscription.current_period_end) : "the period ends"},
              since that is what you have paid for. After that the workspace
              moves to the Free plan. You can undo this at any time before then.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isBusy}>Keep subscription</AlertDialogCancel>
            <AlertDialogAction onClick={cancel} disabled={isBusy}>
              Cancel at period end
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
