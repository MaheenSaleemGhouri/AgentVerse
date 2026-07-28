import { notFound } from "next/navigation";

import { listAgents } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import { getInstalled } from "@/lib/api/integrations";

import { ServerDetail } from "@/components/integrations/server-detail";

export default async function IntegrationDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string; installedServerId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, installedServerId } = await params;

  try {
    // In parallel: the access tab needs the agent list to resolve names,
    // and serialising them would double time to first paint for no gain.
    const [server, agents] = await Promise.all([
      getInstalled(workspaceId, installedServerId),
      listAgents(workspaceId),
    ]);
    return (
      <ServerDetail workspaceId={workspaceId} initialServer={server} agents={agents} />
    );
  } catch (error) {
    // The API returns 404 for an integration in another workspace as
    // well as one that does not exist — deliberately indistinguishable,
    // so this renders the same not-found either way.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

export const metadata = {
  title: "Integration · AgentVerse",
};
