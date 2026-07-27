"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { Team } from "@/lib/api/teams";
import { formatMicroUsd } from "@/lib/format";
import { useTeam, useTeamAnalytics } from "@/lib/queries/teams";
import { TOPOLOGIES } from "@/lib/teams-vocabulary";

import { StatCard } from "@/components/patterns/stat-card";
import { RunTeamPanel } from "@/components/teams/run-team-panel";
import { TeamRoster } from "@/components/teams/team-roster";
import { TeamSessionsList } from "@/components/teams/team-sessions-list";
import { TeamSettingsForm } from "@/components/teams/team-settings-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * Team Details — roster, run, history, and settings in one place.
 *
 * Tabs rather than separate routes because all four views operate on the
 * same team object already in the cache; a route change per tab would
 * refetch it and lose the roster edit in progress.
 */
export function TeamDetail({
  workspaceId,
  initialTeam,
  agents,
}: {
  workspaceId: string;
  initialTeam: Team;
  agents: Agent[];
}): React.JSX.Element {
  const { data } = useTeam(workspaceId, initialTeam.id, initialTeam);
  const team = data ?? initialTeam;
  const analytics = useTeamAnalytics(workspaceId, team.id);

  const topology = TOPOLOGIES[team.topology];
  const TopologyIcon = topology.icon;

  const publishedAgentIds = React.useMemo(
    () => new Set(agents.filter((a) => a.published_version_id !== null).map((a) => a.id)),
    [agents]
  );
  const canRun =
    team.members.length > 0 &&
    team.members.some((member) => publishedAgentIds.has(member.agent_id));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start gap-3">
        <Button variant="ghost" size="icon-sm" asChild aria-label="Back to teams">
          <Link href={`/dashboard/${workspaceId}/teams`}>
            <ArrowLeft />
          </Link>
        </Button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{team.name}</h1>
            <Badge variant="outline" className="gap-1.5">
              <TopologyIcon className="size-3" aria-hidden="true" />
              {topology.label}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{topology.summary}</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Members" value={String(team.members.length)} />
        <StatCard
          label="Sessions"
          value={analytics.data ? String(analytics.data.total_sessions) : "—"}
        />
        <StatCard
          label="Handoffs"
          value={analytics.data ? String(analytics.data.total_handoffs) : "—"}
        />
        <StatCard
          label="Total cost"
          value={analytics.data ? formatMicroUsd(analytics.data.total_cost_micro_usd) : "—"}
        />
      </div>

      <Tabs defaultValue="roster">
        <TabsList>
          <TabsTrigger value="roster">Roster</TabsTrigger>
          <TabsTrigger value="run">Run</TabsTrigger>
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="roster" className="mt-5">
          <TeamRoster workspaceId={workspaceId} team={team} agents={agents} />
        </TabsContent>

        <TabsContent value="run" className="mt-5">
          <RunTeamPanel workspaceId={workspaceId} team={team} canRun={canRun} />
        </TabsContent>

        <TabsContent value="sessions" className="mt-5">
          <TeamSessionsList workspaceId={workspaceId} team={team} />
        </TabsContent>

        <TabsContent value="settings" className="mt-5">
          <TeamSettingsForm workspaceId={workspaceId} team={team} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
