"use client";

import { FileSearch } from "lucide-react";
import * as React from "react";

import { listAuditLogsAction } from "@/lib/api/actions";
import type { AuditLogEntry, AuditLogPage } from "@/lib/api/audit-logs";
import { formatDateTime } from "@/lib/format";
import { useAuditLogs } from "@/lib/queries/audit-logs";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const OUTCOME_TONE: Record<string, "success" | "danger" | "neutral"> = {
  success: "success",
  denied: "danger",
  failure: "danger",
};

export function AuditLogTable({
  workspaceId,
  initialPage,
}: {
  workspaceId: string;
  initialPage?: AuditLogPage;
}): React.JSX.Element {
  // Raw input state, separate from the committed filter values that
  // actually drive the query: filtering fires on Enter/blur rather than
  // per keystroke, so typing "permission.denied" doesn't issue a dozen
  // requests along the way.
  const [actionInput, setActionInput] = React.useState("");
  const [actorInput, setActorInput] = React.useState("");
  const [committedAction, setCommittedAction] = React.useState("");
  const [committedActor, setCommittedActor] = React.useState("");

  const filters = {
    ...(committedAction ? { action: committedAction } : {}),
    ...(committedActor ? { actor_user_id: committedActor } : {}),
  };

  const {
    data: firstPage,
    isError,
    refetch,
    isLoading,
  } = useAuditLogs(workspaceId, filters, initialPage);

  // Pages beyond the first are accumulated locally rather than through
  // react-query's cache — there is no existing infinite-query pattern in
  // this codebase to extend, and a workspace's audit history is read far
  // more often than it grows, so refetching everything on a filter
  // change (which resets this) is the simpler, correct-by-construction
  // choice over introducing a new pagination abstraction for one screen.
  const [extraEntries, setExtraEntries] = React.useState<AuditLogEntry[]>([]);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = React.useState(false);
  const [loadMoreError, setLoadMoreError] = React.useState(false);

  const filtersKey = `${committedAction}:${committedActor}`;
  const previousFiltersKey = React.useRef(filtersKey);
  if (previousFiltersKey.current !== filtersKey) {
    previousFiltersKey.current = filtersKey;
    setExtraEntries([]);
    setCursor(null);
  }

  React.useEffect(() => {
    setCursor(firstPage?.has_more ? (firstPage.next_cursor ?? null) : null);
  }, [firstPage]);

  const entries = [...(firstPage?.data ?? []), ...extraEntries];

  async function loadMore(): Promise<void> {
    if (!cursor) return;
    setIsLoadingMore(true);
    setLoadMoreError(false);
    try {
      const page: AuditLogPage = await listAuditLogsAction(workspaceId, {
        ...filters,
        cursor,
        limit: 50,
      });
      setExtraEntries((prev) => [...prev, ...page.data]);
      setCursor(page.has_more ? (page.next_cursor ?? null) : null);
    } catch {
      setLoadMoreError(true);
    } finally {
      setIsLoadingMore(false);
    }
  }

  if (isError) {
    return (
      <ErrorState
        title="Could not load audit logs"
        description="The workspace API did not respond."
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Filter by action, press Enter…"
          value={actionInput}
          onChange={(event) => setActionInput(event.target.value)}
          onBlur={() => setCommittedAction(actionInput)}
          onKeyDown={(event) => {
            if (event.key === "Enter") setCommittedAction(actionInput);
          }}
          className="max-w-64"
          aria-label="Filter by action"
        />
        <Input
          placeholder="Filter by actor user ID, press Enter…"
          value={actorInput}
          onChange={(event) => setActorInput(event.target.value)}
          onBlur={() => setCommittedActor(actorInput)}
          onKeyDown={(event) => {
            if (event.key === "Enter") setCommittedActor(actorInput);
          }}
          className="max-w-64"
          aria-label="Filter by actor user ID"
        />
      </div>

      {!isLoading && entries.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title="No matching events"
          description={
            committedAction || committedActor
              ? "No audit events match these filters."
              : "Nothing has been recorded for this workspace yet."
          }
        />
      ) : (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-mono text-xs">{entry.action}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {entry.actor_user_id ?? "system"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {entry.target ?? "—"}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone={OUTCOME_TONE[entry.outcome] ?? "neutral"}>
                      {entry.outcome}
                    </StatusBadge>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatDateTime(entry.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {cursor && (
        <div className="flex flex-col items-center gap-2">
          <Button variant="outline" onClick={() => void loadMore()} disabled={isLoadingMore}>
            {isLoadingMore ? "Loading…" : "Load more"}
          </Button>
          {loadMoreError && (
            <p className="text-xs text-destructive">
              Could not load more entries. Try again.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
