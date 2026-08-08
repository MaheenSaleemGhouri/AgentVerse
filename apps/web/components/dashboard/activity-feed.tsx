import { Activity } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { AuditLogEntry } from "@/lib/api/audit-logs";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/patterns/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

/**
 * What has actually happened in this workspace.
 *
 * Sourced from `audit_logs`, which is the only durable record of
 * workspace events that has a read path today. The approved reference
 * shows agent runs in this panel; runs cannot be read back
 * (`feature-availability.ts` → `runHistory`), so this shows the real
 * events that exist rather than inventing the ones that do not.
 *
 * Audit reading is admin-gated, so `entries` is `null` for members and
 * viewers — a different state from "nothing happened", and rendered
 * differently.
 */

/** `agent.created` → "Agent created". One transformation, so a new
 * backend action gets a readable label without a lookup table that has
 * to be kept in sync with an enum it does not own. */
function humanizeAction(action: string): string {
  const words = action.replace(/[._]/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const OUTCOME_TONE: Record<string, string> = {
  success: "bg-success",
  denied: "bg-destructive",
  failure: "bg-destructive",
};

export function ActivityFeed({
  workspaceId,
  entries,
  canRead,
}: {
  workspaceId: string;
  entries: AuditLogEntry[];
  /** False when the caller's role cannot read the audit trail. */
  canRead: boolean;
}): React.JSX.Element {
  if (!canRead) {
    return (
      <Card className="gap-2 p-6">
        <h2 className="font-display text-base font-semibold tracking-tight">Recent activity</h2>
        <p className="text-sm text-muted-foreground">
          The workspace activity trail is visible to admins and owners. Your own agents and
          knowledge bases are on this page above.
        </p>
      </Card>
    );
  }

  return (
    <Card className="gap-0 p-0">
      <div className="flex items-center justify-between px-6 py-4">
        <h2 className="font-display text-base font-semibold tracking-tight">Recent activity</h2>
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/dashboard/${workspaceId}/audit-logs`}>View all</Link>
        </Button>
      </div>

      {entries.length === 0 ? (
        <div className="px-6 pb-6">
          <EmptyState
            icon={Activity}
            title="Nothing has happened yet"
            description="Agent, knowledge, member and billing events appear here as they occur."
          />
        </div>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {entries.map((entry) => (
            <li key={entry.id} className="flex items-start gap-3 px-6 py-3">
              {/* The dot reinforces the outcome; the outcome is also in
                  the text below it, so nothing here is colour-only. */}
              <span
                aria-hidden="true"
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  OUTCOME_TONE[entry.outcome] ?? "bg-muted-foreground"
                )}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{humanizeAction(entry.action)}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {entry.outcome}
                  {entry.target ? ` · ${entry.target}` : ""}
                </p>
              </div>
              <time
                dateTime={entry.created_at}
                className="shrink-0 text-xs text-muted-foreground tabular-nums"
              >
                {formatRelativeTime(entry.created_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
