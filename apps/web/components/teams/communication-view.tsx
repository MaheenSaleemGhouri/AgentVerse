"use client";

import { MessagesSquare } from "lucide-react";
import * as React from "react";

import type { Team } from "@/lib/api/teams";
import { formatDateTime } from "@/lib/format";
import { useSessionCommunications } from "@/lib/queries/teams";
import { COMMUNICATION_KINDS, TEAM_ROLES } from "@/lib/teams-vocabulary";
import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * The Agent Communication view: every structured message exchanged
 * during one session.
 *
 * Agents never exchange free text between themselves — every message is
 * one of a fixed set of kinds carrying a typed payload — so this renders
 * as a filterable log with the kind stated, not as a chat transcript
 * that would imply a conversation that did not happen.
 */
const KIND_ORDER = [
  "task_request",
  "task_result",
  "context_share",
  "intermediate_result",
  "error_report",
] as const;

type Filter = "all" | (typeof KIND_ORDER)[number];

export function CommunicationView({
  workspaceId,
  team,
  sessionId,
}: {
  workspaceId: string;
  team: Team;
  sessionId: string;
}): React.JSX.Element {
  const { data: messages, isLoading, isError, refetch } = useSessionCommunications(
    workspaceId,
    team.id,
    sessionId
  );
  const [filter, setFilter] = React.useState<Filter>("all");

  const roleOf = React.useCallback(
    (agentId: string | null): string => {
      if (!agentId) return "Orchestrator";
      const member = team.members.find((candidate) => candidate.agent_id === agentId);
      return member ? TEAM_ROLES[member.role].label : agentId.slice(0, 8);
    },
    [team.members]
  );

  const visible = React.useMemo(
    () => (messages ?? []).filter((message) => filter === "all" || message.kind === filter),
    [messages, filter]
  );

  if (isError) {
    return (
      <ErrorState
        title="Could not load the message log"
        description="The orchestration service did not respond. The session itself is unaffected."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-16 rounded-lg" />
        ))}
      </div>
    );
  }

  if ((messages ?? []).length === 0) {
    return (
      <EmptyState
        icon={MessagesSquare}
        title="No messages in this session"
        description="Members exchange structured messages as they hand work between each other. This session finished before any were sent."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          {KIND_ORDER.map((kind) => (
            <TabsTrigger key={kind} value={kind}>
              {COMMUNICATION_KINDS[kind]?.label ?? kind}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {visible.length === 0 ? (
        <EmptyState
          icon={MessagesSquare}
          title="No messages of that kind"
          description="Try another filter, or view all messages."
        />
      ) : (
        <ol className="flex flex-col gap-2">
          {visible.map((message) => {
            const meta = COMMUNICATION_KINDS[message.kind];
            const Icon = meta?.icon ?? MessagesSquare;
            const isError = message.kind === "error_report";
            const body =
              typeof message.content.output === "string"
                ? message.content.output
                : typeof message.content.task === "string"
                  ? message.content.task
                  : typeof message.content.error === "string"
                    ? message.content.error
                    : JSON.stringify(message.content);

            return (
              <li
                key={message.id}
                className={cn(
                  "flex gap-3 rounded-lg border p-3",
                  isError ? "border-destructive/30 bg-destructive-soft/40" : "border-border"
                )}
              >
                <Icon
                  className={cn(
                    "mt-0.5 size-4 shrink-0",
                    isError ? "text-destructive" : "text-muted-foreground"
                  )}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{roleOf(message.from_agent_id)}</span>
                    {message.to_agent_id && (
                      <span className="text-xs text-muted-foreground">
                        → {roleOf(message.to_agent_id)}
                      </span>
                    )}
                    <Badge variant="outline" className="text-xs">
                      {meta?.label ?? message.kind}
                    </Badge>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatDateTime(message.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm break-words whitespace-pre-wrap">{body}</p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
