"use client";

import { History } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Team } from "@/lib/api/teams";
import { formatDuration, formatMicroUsd, formatRelativeTime } from "@/lib/format";
import { isSessionActive, useTeamSessions } from "@/lib/queries/teams";
import { sessionTone } from "@/lib/teams-vocabulary";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/** Session history for one team, newest first. */
export function TeamSessionsList({
  workspaceId,
  team,
}: {
  workspaceId: string;
  team: Team;
}): React.JSX.Element {
  const { data, isLoading, isError, refetch } = useTeamSessions(workspaceId, team.id);

  if (isError) {
    return (
      <ErrorState
        title="Could not load session history"
        description="The orchestration service did not respond. Past sessions are unaffected."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-12 rounded-lg" />
        ))}
      </div>
    );
  }

  const sessions = data?.data ?? [];
  if (sessions.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="This team has not run yet"
        description="Start it from the Run tab. Every session is kept here with its full handoff and message record."
      />
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Prompt</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Turns</TableHead>
          <TableHead className="text-right">Cost</TableHead>
          <TableHead className="text-right">Duration</TableHead>
          <TableHead className="text-right">Started</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sessions.map((session) => {
          const prompt =
            typeof session.input.prompt === "string" ? session.input.prompt : "(no prompt)";
          return (
            <TableRow key={session.id}>
              <TableCell className="max-w-xs">
                <Link
                  href={`/dashboard/${workspaceId}/teams/${team.id}/sessions/${session.id}`}
                  className="line-clamp-1 hover:underline"
                >
                  {prompt}
                </Link>
              </TableCell>
              <TableCell>
                <StatusBadge
                  tone={sessionTone(session.status)}
                  pulse={isSessionActive(session.status)}
                >
                  {session.status}
                </StatusBadge>
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {session.total_turns}
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {session.cost_micro_usd === null ? "—" : formatMicroUsd(session.cost_micro_usd)}
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                {session.started_at
                  ? formatDuration(session.started_at, session.completed_at)
                  : "—"}
              </TableCell>
              <TableCell className="text-right text-xs text-muted-foreground">
                {formatRelativeTime(session.created_at)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
