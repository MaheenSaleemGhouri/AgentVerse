import { ArrowUpRight, Clock } from "lucide-react";
import * as React from "react";

import { PENDING_INTEGRATIONS, type PendingIntegrationKey } from "@/lib/feature-availability";

import { Card } from "@/components/ui/card";

/**
 * Renders the honest state of a screen whose backend has not shipped.
 *
 * Deliberately *not* a fake dashboard. It names the capability, the
 * exact endpoints the screen will call, and the roadmap phase that
 * delivers them — so this panel doubles as the integration checklist for
 * whoever wires it up, and a user is never shown a number that isn't
 * real.
 */
export function IntegrationPending({
  feature,
  children,
}: {
  feature: PendingIntegrationKey;
  /** Optional preview of the real layout, rendered above the notice. */
  children?: React.ReactNode;
}): React.JSX.Element {
  const pending = PENDING_INTEGRATIONS[feature];

  return (
    <div className="space-y-6">
      {children}
      <Card className="gap-0 border-dashed p-6">
        <div className="flex items-start gap-4">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground">
            <Clock className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 space-y-3">
            <div className="space-y-1">
              <p className="font-medium text-foreground">Backend not connected yet</p>
              <p className="text-sm text-muted-foreground">{pending.capability}</p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Integration point
              </p>
              <ul className="space-y-1">
                {pending.endpoints.map((endpoint) => (
                  <li
                    key={endpoint}
                    className="rounded-md bg-muted px-2.5 py-1.5 font-mono text-xs break-all text-foreground"
                  >
                    {endpoint}
                  </li>
                ))}
              </ul>
            </div>

            <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <ArrowUpRight className="size-3.5" aria-hidden="true" />
              Delivered by Phase {pending.phase} — {pending.phaseName}
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
