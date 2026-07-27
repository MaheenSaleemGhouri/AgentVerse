"use client";

import { Play } from "lucide-react";
import * as React from "react";

import type { Team } from "@/lib/api/teams";
import { useExecuteTeam } from "@/lib/queries/teams";
import { useTeamSessionStream } from "@/lib/hooks/useTeamSessionStream";

import { TeamRuntimeMonitor } from "@/components/teams/team-runtime-monitor";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

/**
 * Start a team and watch it work.
 *
 * The session id is held in local state rather than a route param: this
 * panel is a launcher, and navigating away from the builder to see the
 * result would lose the roster the user is still editing. A finished
 * session is reachable from the sessions list, which is where it
 * belongs permanently.
 */
export function RunTeamPanel({
  workspaceId,
  team,
  canRun,
}: {
  workspaceId: string;
  team: Team;
  canRun: boolean;
}): React.JSX.Element {
  const [prompt, setPrompt] = React.useState("");
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const execute = useExecuteTeam(workspaceId, team.id);

  const stream = useTeamSessionStream(workspaceId, team.id, sessionId);

  async function onRun(): Promise<void> {
    const session = await execute.mutateAsync(prompt.trim());
    setSessionId(session.id);
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_minmax(0,420px)]">
      <Card className="h-fit gap-3 p-5">
        <div>
          <h2 className="text-sm font-medium">Run this team</h2>
          <p className="text-xs text-muted-foreground">
            {canRun
              ? "Every member runs against your prompt using its own published configuration."
              : "Add members and publish at least one of their agents before running."}
          </p>
        </div>

        <Textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={4}
          placeholder="Research our top competitor's pricing and draft a one-page comparison."
          aria-label="Prompt for the team"
          disabled={!canRun}
        />

        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            Bounded at {team.max_turns} turns and {team.timeout_seconds}s.
          </p>
          <Button
            onClick={() => void onRun()}
            disabled={!canRun || !prompt.trim() || execute.isPending}
          >
            <Play />
            {execute.isPending ? "Starting…" : "Run team"}
          </Button>
        </div>
      </Card>

      <TeamRuntimeMonitor
        team={team}
        events={stream.events}
        status={sessionId ? stream.status : "idle"}
        totalCostMicroUsd={stream.totalCostMicroUsd}
        activeAgentIds={stream.activeAgentIds}
        handoffCount={stream.handoffCount}
        sessionId={sessionId}
      />
    </div>
  );
}
