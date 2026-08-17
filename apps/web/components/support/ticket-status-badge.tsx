import * as React from "react";

import { StatusBadge } from "@/components/patterns/status-badge";

const TONES = {
  triaging: "info",
  triaged: "success",
  resolved: "neutral",
  failed: "danger",
} as const;

const LABELS = {
  triaging: "Triaging",
  triaged: "Triaged",
  resolved: "Resolved",
  failed: "Failed",
} as const;

export function TicketStatusBadge({ status }: { status: string }): React.JSX.Element {
  const key = status in TONES ? (status as keyof typeof TONES) : "triaging";
  return (
    <StatusBadge tone={TONES[key]} pulse={key === "triaging"}>
      {LABELS[key]}
    </StatusBadge>
  );
}
