import { notFound } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { getAgent, getLatestVersion } from "@/lib/api/agents";

import { AgentBuilder } from "@/components/agents/agent-builder";

export default async function AgentBuilderPage({
  params,
}: {
  params: Promise<{ workspaceId: string; agentId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, agentId } = await params;

  const agent = await getAgent(workspaceId, agentId).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  });
  if (!agent) {
    notFound();
  }

  const version = await getLatestVersion(workspaceId, agentId);
  if (!version) {
    // Every agent is created with a first version in the same
    // transaction (create_agent.py) — reaching here means the agent
    // is in a state this UI doesn't support editing.
    notFound();
  }

  return <AgentBuilder workspaceId={workspaceId} agent={agent} version={version} />;
}
