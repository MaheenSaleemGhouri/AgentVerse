import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";
import { env } from "@/lib/env";

/**
 * Every type below is generated from the API's OpenAPI schema — never
 * hand-written, so a backend field rename fails the build here rather
 * than becoming `undefined` at runtime.
 */
export type Plan = components["schemas"]["PlanResponse"];
export type Subscription = components["schemas"]["SubscriptionResponse"];
export type SubscriptionEvent = components["schemas"]["SubscriptionEventResponse"];
export type Entitlements = components["schemas"]["EntitlementsResponse"];
export type EntitlementLine = components["schemas"]["EntitlementLineResponse"];
export type PeriodUsage = components["schemas"]["PeriodUsageResponse"];
export type DraftInvoice = components["schemas"]["DraftInvoiceResponse"];
export type Invoice = components["schemas"]["InvoiceResponse"];
export type PaymentMethod = components["schemas"]["PaymentMethodResponse"];
export type CreditBalance = components["schemas"]["CreditBalanceResponse"];
export type ReferralSummary = components["schemas"]["ReferralSummaryResponse"];
export type PlanChangeQuote = components["schemas"]["PlanChangeQuoteResponse"];
export type BillingInterval = components["schemas"]["BillingInterval"];
export type PlanTier = components["schemas"]["PlanTier"];

/**
 * The published catalog, read without a session.
 *
 * `/api/v1/plans` is deliberately unauthenticated — it is the pricing
 * page's data, and the pricing page has no session. `apiFetch` requires
 * one, so this is the one billing call that goes direct.
 */
export async function listPublicPlans(): Promise<Plan[]> {
  const response = await fetch(`${env.apiInternalUrl}/api/v1/plans`, {
    // Pricing changes are an operational edit to the `plans` table, not
    // a deploy, so a long-lived cache would serve a price the product no
    // longer sells. A minute is short enough to be honest and long
    // enough that a marketing-page spike does not become database load.
    next: { revalidate: 60 },
  });
  if (!response.ok) {
    throw new Error(`Could not load the plan catalog (${response.status})`);
  }
  const body = (await response.json()) as { data: Plan[] };
  return body.data;
}

export async function getSubscription(workspaceId: string): Promise<Subscription> {
  return apiFetch<Subscription>(`/api/v1/workspaces/${workspaceId}/billing/subscription`);
}

export async function getEntitlements(workspaceId: string): Promise<Entitlements> {
  return apiFetch<Entitlements>(`/api/v1/workspaces/${workspaceId}/billing/entitlements`);
}

export async function getUsage(workspaceId: string): Promise<PeriodUsage> {
  return apiFetch<PeriodUsage>(`/api/v1/workspaces/${workspaceId}/billing/usage`);
}

export async function getInvoicePreview(workspaceId: string): Promise<DraftInvoice> {
  return apiFetch<DraftInvoice>(`/api/v1/workspaces/${workspaceId}/billing/invoice-preview`);
}

export async function listInvoices(workspaceId: string): Promise<Invoice[]> {
  const body = await apiFetch<{ data: Invoice[] }>(
    `/api/v1/workspaces/${workspaceId}/billing/invoices`
  );
  return body.data;
}

export async function listPaymentMethods(workspaceId: string): Promise<PaymentMethod[]> {
  const body = await apiFetch<{ data: PaymentMethod[] }>(
    `/api/v1/workspaces/${workspaceId}/billing/payment-methods`
  );
  return body.data;
}

export async function getCredits(workspaceId: string): Promise<CreditBalance> {
  return apiFetch<CreditBalance>(`/api/v1/workspaces/${workspaceId}/billing/credits`);
}

export async function getReferrals(workspaceId: string): Promise<ReferralSummary> {
  return apiFetch<ReferralSummary>(`/api/v1/workspaces/${workspaceId}/billing/referrals`);
}

export async function getSubscriptionEvents(workspaceId: string): Promise<SubscriptionEvent[]> {
  const body = await apiFetch<{ data: SubscriptionEvent[] }>(
    `/api/v1/workspaces/${workspaceId}/billing/subscription/events`
  );
  return body.data;
}

export async function createCheckoutSession(
  workspaceId: string,
  body: { plan_slug: PlanTier; interval: BillingInterval; coupon_code?: string | null }
): Promise<{ checkout_url: string; session_id: string }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/checkout-session`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function createPortalSession(
  workspaceId: string
): Promise<{ portal_url: string }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/portal-session`, {
    method: "POST",
  });
}

export async function quotePlanChange(
  workspaceId: string,
  body: { plan_slug: PlanTier; interval: BillingInterval }
): Promise<PlanChangeQuote> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/subscription/quote`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function changePlan(
  workspaceId: string,
  body: { plan_slug: PlanTier; interval: BillingInterval },
  idempotencyKey: string
): Promise<Subscription> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/subscription/change-plan`, {
    method: "POST",
    // Required by the endpoint: without it a retried request after a
    // timeout applies a second plan change, and each one becomes an
    // invoice line.
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
}

export async function cancelSubscription(
  workspaceId: string,
  body: { at_period_end: boolean; reason?: string | null }
): Promise<Subscription> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/subscription/cancel`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function resumeSubscription(workspaceId: string): Promise<Subscription> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/subscription/resume`, {
    method: "POST",
  });
}

export async function redeemCoupon(
  workspaceId: string,
  code: string
): Promise<{ code: string; credited_cents: number; balance_cents: number }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/billing/credits/redeem`, {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}
