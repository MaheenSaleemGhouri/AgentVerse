import { notFound } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { getTeam, getTeamSession } from "@/lib/api/teams";

import { SessionDetail } from "@/components/teams/session-detail";

export default async function TeamSessionPage({
  params,
}: {
  params: Promise<{ workspaceId: string; teamId: string; sessionId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, teamId, sessionId } = await params;

  try {
    // The team is needed to resolve agent ids to roles in the timeline —
    // a session on its own only carries ids.
    const [team, session] = await Promise.all([
      getTeam(workspaceId, teamId),
      getTeamSession(workspaceId, teamId, sessionId),
    ]);
    return <SessionDetail workspaceId={workspaceId} team={team} initialSession={session} />;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

export const metadata = {
  title: "Team session · AgentVerse",
};
