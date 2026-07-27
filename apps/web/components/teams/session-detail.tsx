"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Team, TeamSession } from "@/lib/api/teams";
import { formatDuration, formatMicroUsd } from "@/lib/format";
import { toTeamEvent, useTeamSessionStream } from "@/lib/hooks/useTeamSessionStream";
import { isSessionActive, useSessionEvents, useTeamSession } from "@/lib/queries/teams";
import { sessionTone } from "@/lib/teams-vocabulary";

import { StatusBadge } from "@/components/patterns/status-badge";
import { CollaborationTimeline } from "@/components/teams/collaboration-timeline";
import { CommunicationView } from "@/components/teams/communication-view";
import { TeamRuntimeMonitor } from "@/components/teams/team-runtime-monitor";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * One team session: live while it runs, a durable record afterwards.
 *
 * The runtime monitor is fed from SSE while the session is in flight and
 * from the persisted `execution_events` once it is not — same event
 * shape either way, which is exactly why the backend publishes and
 * stores one representation rather than two. Opening a finished session
 * must never open a stream that will never receive anything.
 */
export function SessionDetail({
  workspaceId,
  team,
  initialSession,
}: {
  workspaceId: string;
  team: Team;
  initialSession: TeamSession;
}): React.JSX.Element {
  const { data } = useTeamSession(workspaceId, team.id, initialSession.id, initialSession);
  const session = data ?? initialSession;
  const live = isSessionActive(session.status);

  const stream = useTeamSessionStream(workspaceId, team.id, session.id, { enabled: live });
  const persisted = useSessionEvents(workspaceId, team.id, session.id);

  // Persisted events go through the same narrowing as streamed ones, so
  // a finished session renders identically to a live one.
  const events = live ? stream.events : (persisted.data ?? []).map(toTeamEvent);
  const totalCost = live
    ? stream.totalCostMicroUsd
    : events.reduce((sum, event) => sum + (event.cost_micro_usd ?? 0), 0);
  const handoffCount = live
    ? stream.handoffCount
    : events.filter((event) => event.type === "handoff").length;

  const prompt =
    typeof session.input.prompt === "string" ? session.input.prompt : "(no prompt recorded)";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start gap-3">
        <Button variant="ghost" size="icon-sm" asChild aria-label="Back to team">
          <Link href={`/dashboard/${workspaceId}/teams/${team.id}`}>
            <ArrowLeft />
          </Link>
        </Button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{team.name} session</h1>
            <StatusBadge tone={sessionTone(session.status)} pulse={live}>
              {session.status}
            </StatusBadge>
          </div>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{prompt}</p>
        </div>

        <dl className="flex items-center gap-5 text-right">
          <div>
            <dt className="text-xs text-muted-foreground">Turns</dt>
            <dd className="font-mono text-sm tabular-nums">{session.total_turns}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Cost</dt>
            <dd className="font-mono text-sm tabular-nums">
              {session.cost_micro_usd === null ? "—" : formatMicroUsd(session.cost_micro_usd)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Duration</dt>
            <dd className="font-mono text-sm tabular-nums">
              {session.started_at ? formatDuration(session.started_at, session.completed_at) : "—"}
            </dd>
          </div>
        </dl>
      </div>

      {session.error_message && (
        <Alert tone="danger">
          <AlertTitle>This session stopped early</AlertTitle>
          <AlertDescription>{session.error_message}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-5 xl:grid-cols-[1fr_minmax(0,420px)]">
        <div className="flex min-w-0 flex-col gap-5">
          {session.output && (
            <Card className="gap-2 p-5">
              <h2 className="text-sm font-medium">Final answer</h2>
              <p className="text-sm break-words whitespace-pre-wrap">{session.output}</p>
            </Card>
          )}

          <Tabs defaultValue="collaboration">
            <TabsList>
              <TabsTrigger value="collaboration">Collaboration</TabsTrigger>
              <TabsTrigger value="messages">Messages</TabsTrigger>
            </TabsList>

            <TabsContent value="collaboration" className="mt-5">
              <CollaborationTimeline
                workspaceId={workspaceId}
                team={team}
                sessionId={session.id}
              />
            </TabsContent>

            <TabsContent value="messages" className="mt-5">
              <CommunicationView workspaceId={workspaceId} team={team} sessionId={session.id} />
            </TabsContent>
          </Tabs>
        </div>

        <TeamRuntimeMonitor
          team={team}
          events={events}
          status={live ? stream.status : "closed"}
          totalCostMicroUsd={totalCost}
          activeAgentIds={live ? stream.activeAgentIds : []}
          handoffCount={handoffCount}
          sessionId={session.id}
        />
      </div>
    </div>
  );
}
