import * as React from "react";

import type { SupportTicket } from "@/lib/api/support-tickets";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

/**
 * The triage agent's structured output — category/priority/confidence
 * badges plus the draft reply, read-only. Nothing here is ever
 * auto-sent: a human decides whether to use the draft (CLAUDE.md §4
 * Human Approval).
 */
export function TriageResultCard({ ticket }: { ticket: SupportTicket }): React.JSX.Element {
  if (ticket.status === "triaging") {
    return (
      <Card className="p-6">
        <p className="text-sm text-muted-foreground">
          The triage agent is still working on this — refresh in a moment.
        </p>
      </Card>
    );
  }

  if (ticket.status === "failed") {
    return (
      <Card className="p-6">
        <p className="text-sm text-muted-foreground">
          Triage did not produce a usable result. A human will need to categorize this one.
        </p>
      </Card>
    );
  }

  return (
    <Card className="gap-3 p-6">
      <div className="flex flex-wrap items-center gap-2">
        {ticket.category && <Badge variant="secondary">{ticket.category}</Badge>}
        {ticket.priority && <Badge variant="outline">{ticket.priority} priority</Badge>}
        {ticket.confidence && (
          <Badge variant="outline">{ticket.confidence} confidence</Badge>
        )}
      </div>
      {ticket.draft_reply && (
        <div>
          <p className="mb-1 text-sm font-medium text-muted-foreground">Draft reply</p>
          <p className="text-sm whitespace-pre-wrap">{ticket.draft_reply}</p>
        </div>
      )}
    </Card>
  );
}
