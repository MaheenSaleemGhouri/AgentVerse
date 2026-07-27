import { notFound } from "next/navigation";

import { listAgents } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import { getTeam } from "@/lib/api/teams";

import { TeamDetail } from "@/components/teams/team-detail";

export default async function TeamDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string; teamId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, teamId } = await params;

  try {
    // Both in parallel: the roster needs the agent list to resolve names
    // and publication status, and serialising them would double the
    // time to first paint for no benefit.
    const [team, agents] = await Promise.all([
      getTeam(workspaceId, teamId),
      listAgents(workspaceId),
    ]);
    return <TeamDetail workspaceId={workspaceId} initialTeam={team} agents={agents} />;
  } catch (error) {
    // The API returns 404 for a team in another workspace as well as one
    // that does not exist — deliberately indistinguishable, so this
    // renders the same not-found either way.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

export const metadata = {
  title: "Team · AgentVerse",
};
