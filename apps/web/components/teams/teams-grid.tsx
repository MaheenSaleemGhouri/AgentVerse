"use client";

import { Search, Users2 } from "lucide-react";
import * as React from "react";

import type { Team, Topology } from "@/lib/api/teams";
import { useTeams } from "@/lib/queries/teams";
import { TOPOLOGIES } from "@/lib/teams-vocabulary";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { CreateTeamDialog } from "@/components/teams/create-team-dialog";
import { TeamCard } from "@/components/teams/team-card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Filter = "all" | Topology;

const FILTERS: ReadonlyArray<{ value: Filter; label: string }> = [
  { value: "all", label: "All" },
  { value: "supervisor_worker", label: TOPOLOGIES.supervisor_worker.label },
  { value: "sequential", label: TOPOLOGIES.sequential.label },
  { value: "planner_executor_critic", label: TOPOLOGIES.planner_executor_critic.label },
  { value: "parallel", label: TOPOLOGIES.parallel.label },
];

/**
 * Filtering is local UI state, not a query round trip — the full list is
 * already cached, so re-filtering it client-side is instant where a
 * refetch would not be. Same decision as `AgentsGrid`, deliberately.
 */
export function TeamsGrid({
  workspaceId,
  initialTeams,
}: {
  workspaceId: string;
  initialTeams: Team[];
}): React.JSX.Element {
  const { data: teams, isLoading, isError, refetch } = useTeams(workspaceId, initialTeams);
  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState<Filter>("all");

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (teams ?? []).filter((team) => {
      if (filter !== "all" && team.topology !== filter) return false;
      if (!needle) return true;
      return (
        team.name.toLowerCase().includes(needle) ||
        (team.description ?? "").toLowerCase().includes(needle)
      );
    });
  }, [teams, query, filter]);

  if (isError) {
    return (
      <ErrorState
        title="Could not load teams"
        description="The orchestration service did not respond. Your teams are unaffected."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading && !teams) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} className="h-44 rounded-xl" />
        ))}
      </div>
    );
  }

  if ((teams ?? []).length === 0) {
    return (
      <EmptyState
        icon={Users2}
        title="No AI teams yet"
        description="A team runs several of your agents together — one can plan, another research, another write. Start with a supervisor and one specialist."
        action={<CreateTeamDialog workspaceId={workspaceId} />}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search teams"
            aria-label="Search teams"
            className="pl-9"
          />
        </div>

        <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
          <TabsList>
            {FILTERS.map((option) => (
              <TabsTrigger key={option.value} value={option.value}>
                {option.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <CreateTeamDialog workspaceId={workspaceId} />
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No teams match"
          description="Try a different search term, or clear the topology filter."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((team) => (
            <TeamCard key={team.id} workspaceId={workspaceId} team={team} />
          ))}
        </div>
      )}
    </div>
  );
}
