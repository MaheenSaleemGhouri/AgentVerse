import Link from "next/link";
import * as React from "react";

import { BillingDashboard } from "@/components/billing/billing-dashboard";
import { ErrorState } from "@/components/patterns/error-state";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";
import {
  getCreditsAction,
  getEntitlementsAction,
  getInvoicePreviewAction,
  getReferralsAction,
  getSubscriptionAction,
  listInvoicesAction,
  listPaymentMethodsAction,
} from "@/lib/api/actions";
import { listPublicPlans } from "@/lib/api/billing";
import { ApiError } from "@/lib/api/client";

/**
 * Billing.
 *
 * Every number on this page is real. The plan and its limits come from
 * the `plans` catalog that server-side quota enforcement also reads, the
 * usage comes from durable metered-usage events, the credit balance from
 * its own ledger, and invoices from the payment provider itself. Nothing
 * here is fabricated, and nothing renders an `IntegrationPending` panel —
 * the backend it was waiting on has shipped.
 *
 * Fetched server-side and passed down as props (CLAUDE.md §6), so the
 * page is populated on first paint rather than flashing eight skeletons.
 * The reads are issued together because they are independent; doing them
 * sequentially would stack eight round trips onto the first render.
 *
 * Invoices and payment methods resolve to `null` where the environment
 * has no payment provider configured. That is a first-class state — CI,
 * local development and preview environments legitimately run that way —
 * and the panel says so rather than showing an empty list that reads as
 * "you have no invoices".
 */
export default async function BillingPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  const header = (
    <PageHeader
      title="Billing"
      description="Your subscription, usage against quota, credit, and invoices."
      actions={
        <Button variant="outline" asChild>
          <Link href="/pricing">Compare plans</Link>
        </Button>
      }
    />
  );

  let data;
  try {
    const [
      plans,
      subscription,
      entitlements,
      invoicePreview,
      invoices,
      paymentMethods,
      credits,
      referrals,
    ] = await Promise.all([
      listPublicPlans(),
      getSubscriptionAction(workspaceId),
      getEntitlementsAction(workspaceId),
      getInvoicePreviewAction(workspaceId),
      listInvoicesAction(workspaceId),
      listPaymentMethodsAction(workspaceId),
      getCreditsAction(workspaceId),
      getReferralsAction(workspaceId),
    ]);
    data = {
      plans,
      subscription,
      entitlements,
      invoicePreview,
      invoices,
      paymentMethods,
      credits,
      referrals,
    };
  } catch (error) {
    // A member without admin rights cannot read invoices or payment
    // methods. Rather than half-rendering the page, say plainly which
    // part needs a higher role — a bare 403 is the "something went
    // wrong" §6 forbids.
    if (error instanceof ApiError && error.status === 403) {
      return (
        <div className="flex flex-col gap-6">
          {header}
          <ErrorState
            title="You need admin access for billing"
            description="Billing includes invoice amounts and payment methods, so it is limited to workspace admins and owners. Ask an admin for access — your usage against quota is also shown on the dashboard."
          />
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-6">
        {header}
        <ErrorState
          title="Could not load billing"
          description="We could not reach the billing service. Your subscription and usage are unaffected — this page recovers on its own once the service responds."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {header}
      <BillingDashboard
        workspaceId={workspaceId}
        plans={data.plans}
        subscription={data.subscription}
        entitlements={data.entitlements}
        invoicePreview={data.invoicePreview}
        invoices={data.invoices}
        paymentMethods={data.paymentMethods}
        credits={data.credits}
        referrals={data.referrals}
        // Reaching this point means the admin-gated reads succeeded, so
        // this identity is an admin. The flag only decides whether to
        // *render* the controls — every mutating route is gated
        // server-side, which is the actual enforcement (Rule 6).
        canManage
      />
    </div>
  );
}

export const metadata = {
  title: "Billing · AgentVerse",
};
