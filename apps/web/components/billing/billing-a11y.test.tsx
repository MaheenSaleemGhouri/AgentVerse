/**
 * WCAG 2.2 AA regression gate for the Phase 9 billing surfaces
 * (CLAUDE.md §15, Rule 7 — accessibility is a merge gate, not a
 * follow-up).
 *
 * axe-core runs against each component's real rendered output, catching
 * the mechanical failures: missing accessible names, unlabelled
 * controls, broken heading/list/table structure, ARIA misuse.
 *
 * What it deliberately does NOT claim: axe detects a minority of real
 * accessibility problems. Focus order, live-region verbosity and whether
 * the flow is actually usable are manual passes, and treating a green
 * run here as "accessible" is the mistake this comment exists to
 * prevent.
 *
 * Colour contrast is not asserted: jsdom has no layout or computed
 * colour, so axe's contrast rules cannot run and would report false
 * passes. Contrast is covered by `app/design-tokens-contrast.test.ts`
 * against the token ramps themselves.
 *
 * Beyond axe, these also assert the two billing-specific rules that no
 * scanner knows about: an unlimited dimension renders no progress bar
 * (a bar with no maximum has nothing truthful to draw), and a
 * limit-reached state is announced in text rather than by colour alone.
 */

import { cleanup, render, screen } from "@testing-library/react";
import axe from "axe-core";
import * as React from "react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { InvoicesPanel } from "@/components/billing/invoices-panel";
import { PlanCard } from "@/components/billing/plan-card";
import { SubscriptionCard } from "@/components/billing/subscription-card";
import { UsageMeter } from "@/components/billing/usage-meter";
import type {
  DraftInvoice,
  EntitlementLine,
  Invoice,
  Plan,
  Subscription,
} from "@/lib/api/billing";

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
  Element.prototype.scrollIntoView ??= function scrollIntoView(): void {};
  globalThis.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof globalThis.matchMedia;
});

afterEach(cleanup);

// Fixtures are typed from the generated OpenAPI schema, so a backend
// field rename breaks these at type-check rather than silently
// under-testing.

const PRO_PLAN: Plan = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "pro",
  display_name: "Pro",
  description: "For builders shipping agents to production.",
  monthly_price_cents: 2900,
  annual_price_cents: 29000,
  annual_saving_percent: 16,
  currency: "usd",
  trial_days: 14,
  sort_order: 1,
  resource_limits: { agents: 25, seats: 3, knowledge_bases: 10 },
  metered_allowances: { agent_runs: 10000 },
  capabilities: ["multi_agent", "analytics"],
  overage_rates: [
    { dimension: "agent_runs", billing_increment: 1000, price_cents_per_increment: 300 },
  ],
};

const ENTERPRISE_PLAN: Plan = {
  ...PRO_PLAN,
  id: "22222222-2222-2222-2222-222222222222",
  slug: "enterprise",
  display_name: "Enterprise",
  monthly_price_cents: null,
  annual_price_cents: null,
  annual_saving_percent: null,
  trial_days: 0,
  overage_rates: [],
};

const ACTIVE_SUBSCRIPTION: Subscription = {
  id: "33333333-3333-3333-3333-333333333333",
  workspace_id: "44444444-4444-4444-4444-444444444444",
  plan_slug: "pro",
  status: "active",
  billing_interval: "monthly",
  current_period_start: "2026-08-01T00:00:00Z",
  current_period_end: "2026-09-01T00:00:00Z",
  trial_end: null,
  cancel_at_period_end: false,
  canceled_at: null,
  entitles: true,
  dunning: null,
};

const PAST_DUE_SUBSCRIPTION: Subscription = {
  ...ACTIVE_SUBSCRIPTION,
  status: "past_due",
  dunning: {
    since: "2026-08-10T00:00:00Z",
    deadline: "2026-08-24T00:00:00Z",
    days_remaining: 9,
    next_action: "retry_payment",
  },
};

function line(overrides: Partial<EntitlementLine> = {}): EntitlementLine {
  return {
    dimension: "agent_runs",
    limit: 10000,
    used: 1200,
    remaining: 8800,
    percent_used: 12,
    at_limit: false,
    approaching_limit: false,
    ...overrides,
  };
}

const INVOICE: Invoice = {
  id: "in_1",
  number: "AV-0001",
  status: "paid",
  amount_due_cents: 2900,
  amount_paid_cents: 2900,
  currency: "usd",
  created_at: "2026-08-01T00:00:00Z",
  period_start: "2026-07-01T00:00:00Z",
  period_end: "2026-08-01T00:00:00Z",
  hosted_invoice_url: "https://provider.test/i/in_1",
  invoice_pdf_url: "https://provider.test/i/in_1.pdf",
};

const PREVIEW: DraftInvoice = {
  workspace_id: "44444444-4444-4444-4444-444444444444",
  period_start: "2026-08-01T00:00:00Z",
  period_end: "2026-09-01T00:00:00Z",
  currency: "usd",
  lines: [
    {
      kind: "subscription",
      dimension: null,
      description: "Pro plan (monthly)",
      quantity: 1,
      unit_label: "plan",
      amount_cents: 2900,
    },
  ],
  subtotal_cents: 2900,
  has_overage: false,
};

async function expectNoViolations(container: HTMLElement): Promise<void> {
  const results = await axe.run(container, {
    rules: { "color-contrast": { enabled: false } },
  });
  expect(
    results.violations.map((violation) => `${violation.id}: ${violation.help}`)
  ).toEqual([]);
}

describe("PlanCard", () => {
  it("has no axe violations", async () => {
    const { container } = render(
      <PlanCard plan={PRO_PLAN} interval="monthly" isRecommended />
    );
    await expectNoViolations(container);
  });

  it("shows a custom-priced tier as contact sales rather than $0", async () => {
    // Rendering "$0.00" for Enterprise would be a commitment the product
    // has not made.
    render(<PlanCard plan={ENTERPRISE_PLAN} interval="monthly" />);
    expect(screen.getByText("Contact sales")).toBeTruthy();
    expect(screen.queryByText("$0.00")).toBeNull();
  });

  it("shows the annual saving only on the annual interval", () => {
    const { rerender } = render(<PlanCard plan={PRO_PLAN} interval="monthly" />);
    expect(screen.queryByText(/Save 16%/)).toBeNull();
    rerender(<PlanCard plan={PRO_PLAN} interval="annual" />);
    expect(screen.getByText(/Save 16%/)).toBeTruthy();
  });

  it("renders an unlimited limit as text, never as a number", () => {
    render(
      <PlanCard
        plan={{ ...PRO_PLAN, resource_limits: { agents: null } }}
        interval="monthly"
      />
    );
    expect(screen.getByText("Unlimited agents")).toBeTruthy();
  });
});

describe("UsageMeter", () => {
  it("has no axe violations", async () => {
    const { container } = render(<UsageMeter line={line()} />);
    await expectNoViolations(container);
  });

  it("draws no progress bar for an unlimited dimension", () => {
    // A bar with no maximum has nothing truthful to draw; rendering one
    // at an arbitrary fill would be a fabricated number.
    render(
      <UsageMeter
        line={line({ limit: null, remaining: null, percent_used: null })}
      />
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("No limit on this plan")).toBeTruthy();
  });

  it("announces a reached limit in text, not by colour alone", () => {
    // CLAUDE.md §15: status is never conveyed by colour alone.
    render(<UsageMeter line={line({ used: 10000, remaining: 0, percent_used: 100, at_limit: true })} />);
    expect(screen.getByText(/Limit reached/)).toBeTruthy();
  });

  it("announces the approaching-limit nudge in text", () => {
    render(
      <UsageMeter line={line({ used: 8500, percent_used: 85, approaching_limit: true })} />
    );
    expect(screen.getByText(/85% of your allowance used/)).toBeTruthy();
  });

  it("gives the progress bar an accessible name including both numbers", () => {
    render(<UsageMeter line={line()} />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-label")).toContain("1,200");
    expect(bar.getAttribute("aria-label")).toContain("10,000");
  });
});

describe("SubscriptionCard", () => {
  it("has no axe violations for an active subscription", async () => {
    const { container } = render(
      <SubscriptionCard
        subscription={ACTIVE_SUBSCRIPTION}
        plan={PRO_PLAN}
        canManage
        providerConfigured
      />
    );
    await expectNoViolations(container);
  });

  it("has no axe violations for a workspace with no subscription", async () => {
    const { container } = render(
      <SubscriptionCard
        subscription={null}
        plan={PRO_PLAN}
        canManage
        providerConfigured
      />
    );
    await expectNoViolations(container);
  });

  it("names the dunning deadline rather than warning vaguely", async () => {
    // A customer who knows the date can act; one told "payment issue"
    // cannot.
    const { container } = render(
      <SubscriptionCard
        subscription={PAST_DUE_SUBSCRIPTION}
        plan={PRO_PLAN}
        canManage
        providerConfigured
      />
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Aug 24, 2026/)).toBeTruthy();
    await expectNoViolations(container);
  });

  it("says payments are unconfigured rather than silently disabling actions", () => {
    render(
      <SubscriptionCard
        subscription={ACTIVE_SUBSCRIPTION}
        plan={PRO_PLAN}
        canManage
        providerConfigured={false}
        onManage={() => {}}
      />
    );
    expect(screen.getByText(/Payments are not configured/)).toBeTruthy();
  });
});

describe("InvoicesPanel", () => {
  it("has no axe violations", async () => {
    const { container } = render(
      <InvoicesPanel invoices={[INVOICE]} preview={PREVIEW} />
    );
    await expectNoViolations(container);
  });

  it("distinguishes an unconfigured provider from an empty invoice list", () => {
    // An empty list would read as "you have no invoices", which is a
    // different and misleading claim.
    const { rerender } = render(<InvoicesPanel invoices={null} preview={null} />);
    expect(screen.getByText(/Payments are not configured here/)).toBeTruthy();

    rerender(<InvoicesPanel invoices={[]} preview={null} />);
    expect(screen.queryByText(/Payments are not configured here/)).toBeNull();
    expect(screen.getByText(/No invoices yet/)).toBeTruthy();
  });

  it("labels each invoice action with the invoice it belongs to", () => {
    // Three identical "download" buttons in a table are unusable with a
    // screen reader.
    render(<InvoicesPanel invoices={[INVOICE]} preview={null} />);
    expect(screen.getByText("Download invoice AV-0001 as PDF")).toBeTruthy();
    expect(screen.getByText("View invoice AV-0001")).toBeTruthy();
  });

  it("labels the preview as an estimate, not a charge", () => {
    render(<InvoicesPanel invoices={[]} preview={PREVIEW} />);
    expect(screen.getByText(/Nothing is charged until the period closes/)).toBeTruthy();
    expect(screen.getByText("Estimated total")).toBeTruthy();
  });
});
