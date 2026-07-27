import { Check } from "lucide-react";

import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { Card } from "@/components/ui/card";

/**
 * Billing.
 *
 * Deliberately shows no current plan, no usage bar, and no invoices —
 * every one of those would be a fabricated number about someone's money.
 * The tier structure is real product information (it is the committed
 * four-tier packaging), so it is shown as reference; the account's actual
 * state waits on the Stripe integration.
 */
const TIERS = [
  {
    name: "Free",
    audience: "Individual builders getting started",
    features: ["Personal workspace", "Community support", "Usage-capped agent runs"],
  },
  {
    name: "Pro",
    audience: "Individual builders shipping to production",
    features: ["Higher run quota", "Usage-based overage", "Email support"],
  },
  {
    name: "Team",
    audience: "Teams collaborating on agents",
    features: ["Multiple seats", "Shared workspaces", "Full observability retention"],
  },
  {
    name: "Enterprise",
    audience: "Organisations with compliance requirements",
    features: ["SSO", "Audit logs", "Dedicated resources", "SLA"],
  },
];

export default function BillingPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Billing"
        description="Your subscription, usage against quota, and invoices."
      />

      <IntegrationPending feature="billing">
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">Tiers</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {TIERS.map((tier) => (
              <Card key={tier.name} className="gap-3 p-5">
                <div>
                  <p className="font-medium">{tier.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{tier.audience}</p>
                </div>
                <ul className="space-y-1.5">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex gap-2 text-sm text-muted-foreground">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden="true" />
                      {feature}
                    </li>
                  ))}
                </ul>
                {/* No price shown: price points are set as part of the
                    billing phase, and inventing them here would be a
                    commitment the product has not made. */}
                <p className="mt-auto pt-2 text-xs text-muted-foreground">
                  Pricing published with the billing release
                </p>
              </Card>
            ))}
          </div>
        </section>
      </IntegrationPending>
    </div>
  );
}

export const metadata = {
  title: "Billing · AgentVerse",
};
