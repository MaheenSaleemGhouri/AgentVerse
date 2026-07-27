"use client";

import { ArrowRightLeft, FileText, Lightbulb, Package } from "lucide-react";
import * as React from "react";

import type { Handoff, Team } from "@/lib/api/teams";
import { formatDateTime } from "@/lib/format";
import { useSessionHandoffs } from "@/lib/queries/teams";
import { HANDOFF_KINDS, TEAM_ROLES } from "@/lib/teams-vocabulary";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";

interface Finding {
  label: string;
  detail: string;
  confidence?: number;
}

/**
 * Reads the stored `HandoffContract` off a handoff row.
 *
 * The contract is deliberately a typed payload rather than a transcript,
 * and this is where that pays off: findings render as rows, memory keys
 * as chips, and pointers as links — none of which is possible with a
 * conversation dump.
 */
function contractOf(handoff: Handoff): {
  summary: string;
  nextTask: string | null;
  findings: Finding[];
  memoryKeys: string[];
  sourceDocumentIds: string[];
} {
  const raw = handoff.contract as Record<string, unknown>;
  const findings = Array.isArray(raw.findings) ? (raw.findings as Finding[]) : [];
  return {
    summary: typeof raw.summary === "string" ? raw.summary : "(no summary)",
    nextTask: typeof raw.next_task === "string" ? raw.next_task : null,
    findings,
    memoryKeys: Array.isArray(raw.memory_keys) ? (raw.memory_keys as string[]) : [],
    sourceDocumentIds: Array.isArray(raw.source_document_ids)
      ? (raw.source_document_ids as string[])
      : [],
  };
}

/**
 * The Collaboration Timeline: every transfer of control in one session,
 * in order, with what actually crossed each boundary.
 *
 * `kind` is shown, not hidden behind a generic "handoff" label —
 * "the model chose to delegate" and "the topology moved to the next
 * stage" are different facts, and the first question asked when a team
 * routes badly is which one happened.
 */
export function CollaborationTimeline({
  workspaceId,
  team,
  sessionId,
}: {
  workspaceId: string;
  team: Team;
  sessionId: string;
}): React.JSX.Element {
  const { data: handoffs, isLoading, isError, refetch } = useSessionHandoffs(
    workspaceId,
    team.id,
    sessionId
  );

  const roleOf = React.useCallback(
    (agentId: string | null): string => {
      if (!agentId) return "Orchestrator";
      const member = team.members.find((candidate) => candidate.agent_id === agentId);
      return member ? TEAM_ROLES[member.role].label : agentId.slice(0, 8);
    },
    [team.members]
  );

  if (isError) {
    return (
      <ErrorState
        title="Could not load the handoff history"
        description="The orchestration service did not respond. The session itself is unaffected."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} className="h-20 rounded-lg" />
        ))}
      </div>
    );
  }

  if ((handoffs ?? []).length === 0) {
    return (
      <EmptyState
        icon={ArrowRightLeft}
        title="No handoffs in this session"
        description="Control never passed between members — either one agent handled the whole task, or the session ended before delegating."
      />
    );
  }

  return (
    <ol className="flex flex-col gap-3">
      {(handoffs ?? []).map((handoff) => {
        const contract = contractOf(handoff);
        const kind = HANDOFF_KINDS[handoff.kind] ?? {
          label: handoff.kind,
          tone: "neutral" as const,
          explanation: "",
        };

        return (
          <li key={handoff.id}>
            <Card className="gap-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{roleOf(handoff.from_agent_id)}</span>
                <ArrowRightLeft className="size-3.5 text-muted-foreground" aria-hidden="true" />
                <span className="text-sm font-medium">{roleOf(handoff.to_agent_id)}</span>
                <StatusBadge tone={kind.tone}>{kind.label}</StatusBadge>
                <span className="ml-auto text-xs text-muted-foreground">
                  {formatDateTime(handoff.created_at)}
                </span>
              </div>

              {kind.explanation && (
                <p className="text-xs text-muted-foreground">{kind.explanation}</p>
              )}

              <p className="text-sm break-words whitespace-pre-wrap">{contract.summary}</p>

              {contract.nextTask && (
                <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  <span className="text-xs text-muted-foreground">Asked to: </span>
                  {contract.nextTask}
                </p>
              )}

              {(contract.findings.length > 0 ||
                contract.memoryKeys.length > 0 ||
                contract.sourceDocumentIds.length > 0) && (
                <Collapsible>
                  <CollapsibleTrigger className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground">
                    What was passed along
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 flex flex-col gap-2">
                    {contract.findings.length > 0 && (
                      <ul className="flex flex-col gap-1.5">
                        {contract.findings.map((finding) => (
                          <li key={finding.label} className="flex gap-2 text-sm">
                            <Lightbulb
                              className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
                              aria-hidden="true"
                            />
                            <span>
                              <span className="font-medium">{finding.label}:</span>{" "}
                              {finding.detail}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}

                    {contract.memoryKeys.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Package
                          className="size-3.5 text-muted-foreground"
                          aria-hidden="true"
                        />
                        <span className="text-xs text-muted-foreground">
                          Shared memory to read:
                        </span>
                        {contract.memoryKeys.map((key) => (
                          <Badge key={key} variant="secondary" className="font-mono text-xs">
                            {key}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {contract.sourceDocumentIds.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <FileText
                          className="size-3.5 text-muted-foreground"
                          aria-hidden="true"
                        />
                        <span className="text-xs text-muted-foreground">Sources:</span>
                        {contract.sourceDocumentIds.map((id) => (
                          <Badge key={id} variant="outline" className="font-mono text-xs">
                            {id.slice(0, 8)}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </Card>
          </li>
        );
      })}
    </ol>
  );
}
