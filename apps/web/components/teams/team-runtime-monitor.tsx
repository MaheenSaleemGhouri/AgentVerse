"use client";

import {
  ArrowRightLeft,
  CheckCircle2,
  CircleDashed,
  CircleHelp,
  Loader2,
  Play,
  UserCog,
  XCircle,
} from "lucide-react";
import * as React from "react";

import type { Team } from "@/lib/api/teams";
import { formatMicroUsd } from "@/lib/format";
import type { TeamEvent, TeamEventType, TeamStreamStatus } from "@/lib/hooks/useTeamSessionStream";
import { cn } from "@/lib/utils";

import { CopyButton } from "@/components/patterns/copy-button";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

/**
 * The multi-agent Runtime Monitor.
 *
 * Extends the single-agent monitor's model rather than replacing it —
 * same timeline rail, same status vocabulary, same auto-follow rule —
 * with the three things a team run has that a solo run does not: who is
 * running right now, how many handoffs have happened, and which member
 * each event belongs to.
 *
 * Exhaustive over `TeamEventType` with a `never` check, so an event type
 * added to the union fails this build until it is handled here.
 */
const EVENT_ICON: Record<TeamEventType, React.ComponentType<{ className?: string }>> = {
  session_started: Play,
  agent_started: Loader2,
  agent_completed: CheckCircle2,
  agent_failed: XCircle,
  handoff: ArrowRightLeft,
  handoff_unresolved: CircleHelp,
  session_completed: CheckCircle2,
  session_failed: XCircle,
  unknown_event: CircleHelp,
};

function text(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

function summarize(event: TeamEvent, nameOf: (agentId: string | null) => string): string {
  switch (event.type) {
    case "session_started":
      return `${text(event.payload, "team_name") ?? "Team"} started · ${
        text(event.payload, "topology") ?? "unknown topology"
      }`;
    case "agent_started":
      return `${nameOf(event.agent_id)} started working`;
    case "agent_completed":
      return text(event.payload, "output") ?? `${nameOf(event.agent_id)} finished`;
    case "agent_failed":
      return `${nameOf(event.agent_id)} failed: ${text(event.payload, "error") ?? "unknown error"}`;
    case "handoff":
      return `${nameOf(text(event.payload, "from_agent_id"))} → ${nameOf(
        text(event.payload, "to_agent_id")
      )}${text(event.payload, "next_task") ? `: ${text(event.payload, "next_task")}` : ""}`;
    case "handoff_unresolved":
      return `A handoff named "${text(event.payload, "target_name") ?? "an unknown agent"}", which is not on this team`;
    case "session_completed":
      return text(event.payload, "output") ?? "Team finished";
    case "session_failed":
      return `Failed: ${text(event.payload, "reason") ?? "unknown reason"}`;
    case "unknown_event":
      // The one case that cannot be a build error: an older frontend
      // against a newer API mid-rollout. Labelled, never blank.
      return `Unrecognised event "${text(event.payload, "original_type") ?? "?"}" — this view may be out of date.`;
    default: {
      const exhaustive: never = event.type;
      return exhaustive;
    }
  }
}

export function TeamRuntimeMonitor({
  team,
  events,
  status,
  totalCostMicroUsd,
  activeAgentIds,
  handoffCount,
  sessionId,
}: {
  team: Team;
  events: TeamEvent[];
  status: TeamStreamStatus | "idle";
  totalCostMicroUsd: number;
  activeAgentIds: string[];
  handoffCount: number;
  sessionId: string | null;
}): React.JSX.Element {
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const agentNames = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const member of team.members) map.set(member.agent_id, member.role);
    return map;
  }, [team.members]);

  const nameOf = React.useCallback(
    (agentId: string | null): string => {
      if (!agentId) return "Orchestrator";
      const role = agentNames.get(agentId);
      return role ? role.charAt(0).toUpperCase() + role.slice(1) : agentId.slice(0, 8);
    },
    [agentNames]
  );

  // Follow the tail only while live, so someone reading back through a
  // finished session is not yanked to the end.
  React.useEffect(() => {
    if (status !== "streaming") return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [events.length, status]);

  const lastEvent = events.at(-1);

  return (
    <Card className="flex h-fit max-h-[calc(100vh-10rem)] flex-col gap-0 p-0 xl:sticky xl:top-20">
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-sm font-medium">Runtime monitor</h2>
          {sessionId ? (
            <div className="flex items-center gap-1">
              <code className="truncate font-mono text-xs text-muted-foreground">
                {sessionId.slice(0, 8)}
              </code>
              <CopyButton value={sessionId} label="Copy session ID" size="icon-xs" />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No active session</p>
          )}
        </div>
        <MonitorStatus status={status} />
      </div>

      <div className="grid grid-cols-3 divide-x divide-border border-b border-border text-center">
        <Metric label="Running" value={String(activeAgentIds.length)} />
        <Metric label="Handoffs" value={String(handoffCount)} />
        <Metric label="Cost" value={formatMicroUsd(totalCostMicroUsd)} />
      </div>

      {activeAgentIds.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-border px-5 py-3">
          {activeAgentIds.map((agentId) => (
            <StatusBadge key={agentId} tone="info" pulse>
              <UserCog className="size-3" aria-hidden="true" />
              {nameOf(agentId)}
            </StatusBadge>
          ))}
        </div>
      )}

      {/* Announces only the newest event — narrating every step of a
          busy parallel run would drown a screen-reader user. */}
      <p aria-live="polite" className="sr-only">
        {lastEvent ? summarize(lastEvent, nameOf) : "No activity yet."}
      </p>

      <ScrollArea className="min-h-0 flex-1" viewportRef={scrollRef}>
        {events.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">
            {status === "idle"
              ? "Run the team to watch its members work."
              : "Waiting for the first event…"}
          </p>
        ) : (
          <ol className="flex flex-col px-5 py-4">
            {events.map((event, index) => {
              const Icon = EVENT_ICON[event.type];
              const isLast = index === events.length - 1;
              return (
                <li key={`${event.sequence}-${index}`} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "flex size-6 shrink-0 items-center justify-center rounded-full border",
                        event.type === "agent_failed" || event.type === "session_failed"
                          ? "border-destructive/30 bg-destructive-soft text-destructive"
                          : event.type === "handoff"
                            ? "border-primary/30 bg-accent text-accent-foreground"
                            : "border-border bg-muted text-muted-foreground"
                      )}
                    >
                      <Icon
                        className={cn(
                          "size-3",
                          event.type === "agent_started" && "motion-safe:animate-spin"
                        )}
                      />
                    </span>
                    {!isLast && <span className="w-px flex-1 bg-border" aria-hidden="true" />}
                  </div>

                  <div className={cn("min-w-0 flex-1", isLast ? "pb-0" : "pb-4")}>
                    <p className="text-sm break-words whitespace-pre-wrap">
                      {summarize(event, nameOf)}
                    </p>
                    {event.cost_micro_usd !== null && event.cost_micro_usd > 0 && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {formatMicroUsd(event.cost_micro_usd)}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </ScrollArea>

      <Separator />
      <p className="px-5 py-3 text-xs text-muted-foreground">
        Live view. The full record is kept and stays readable after the session ends.
      </p>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="px-3 py-3">
      <p className="font-mono text-sm tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function MonitorStatus({
  status,
}: {
  status: TeamStreamStatus | "idle";
}): React.JSX.Element {
  switch (status) {
    case "idle":
      return (
        <StatusBadge tone="neutral">
          <CircleDashed className="size-3" aria-hidden="true" />
          Idle
        </StatusBadge>
      );
    case "connecting":
      return <StatusBadge tone="info">Connecting</StatusBadge>;
    case "streaming":
      return (
        <StatusBadge tone="info" pulse>
          Live
        </StatusBadge>
      );
    case "closed":
      return <StatusBadge tone="success">Finished</StatusBadge>;
    case "error":
      return <StatusBadge tone="danger">Disconnected</StatusBadge>;
    default: {
      const exhaustive: never = status;
      return exhaustive;
    }
  }
}
