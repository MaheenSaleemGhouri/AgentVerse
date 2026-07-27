import { listTeams } from "@/lib/api/teams";

import { PageHeader } from "@/components/patterns/page-header";
import { TeamsGrid } from "@/components/teams/teams-grid";

export default async function TeamsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  // Server-fetched for first paint; `TeamsGrid` seeds the TanStack Query
  // cache with it so filtering and post-mutation refetches take over
  // without a loading flash (CLAUDE.md §6).
  const teams = await listTeams(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="AI teams"
        description="Run several agents together — one plans, another researches, another writes. Each keeps its own configuration."
      />
      <TeamsGrid workspaceId={workspaceId} initialTeams={teams} />
    </div>
  );
}

export const metadata = {
  title: "AI teams · AgentVerse",
};
