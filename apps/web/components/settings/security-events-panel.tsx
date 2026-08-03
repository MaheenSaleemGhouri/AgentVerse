import { AlertTriangle, Info, ShieldAlert, ShieldCheck } from "lucide-react";
import * as React from "react";

import type { SecurityEvent, SecuritySeverity } from "@/lib/api/security";
import { formatDateTime } from "@/lib/format";

import { EmptyState } from "@/components/patterns/empty-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/** Exhaustive over the severity union — adding a severity to the API
 *  breaks this build rather than silently rendering nothing. */
const SEVERITY_TONE: Record<SecuritySeverity, "neutral" | "warning" | "danger"> = {
  info: "neutral",
  warning: "warning",
  critical: "danger",
};

const SEVERITY_ICON: Record<SecuritySeverity, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  critical: ShieldAlert,
};

/** `login.new_device` reads badly in a UI; these do not. Falls back to
 *  the raw type so a newly added event is still legible rather than
 *  blank. */
const EVENT_LABEL: Record<string, string> = {
  "login.new_device": "Signed in from a new device",
  "login.failed": "Failed sign-in attempt",
  "account.locked": "Account locked",
  "password.changed": "Password changed",
  "two_factor.enabled": "Two-factor enabled",
  "two_factor.disabled": "Two-factor disabled",
  "device.trusted": "Device trusted",
  "device.revoked": "Device revoked",
  "suspicious.ip": "Sign-in from an unusual location",
  "suspicious.rapid_failures": "Repeated failed sign-ins",
};

export function SecurityEventsPanel({
  events,
  title,
  description,
}: {
  events: SecurityEvent[];
  title: string;
  description: string;
}): React.JSX.Element {
  return (
    <Card className="gap-4 p-6">
      <div>
        <h2 className="font-medium">{title}</h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Separator />
      {events.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="Nothing to report"
          description="No security events have been recorded. That is the good outcome."
        />
      ) : (
        <ul className="space-y-3">
          {events.map((event) => {
            const Icon = SEVERITY_ICON[event.severity];
            return (
              <li key={event.id} className="flex items-start gap-3">
                <Icon
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm">
                      {EVENT_LABEL[event.event_type] ?? event.event_type}
                    </span>
                    {/* The badge repeats the severity as text, so it is
                        never conveyed by colour alone. */}
                    <StatusBadge tone={SEVERITY_TONE[event.severity]}>
                      {event.severity}
                    </StatusBadge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(event.created_at)}
                    {event.ip_address ? ` · ${event.ip_address}` : ""}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
