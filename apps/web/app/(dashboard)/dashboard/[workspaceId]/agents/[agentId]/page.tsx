import { MessageSquare, Pencil } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getAgent, getLatestVersion } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import { listKnowledgeBases } from "@/lib/api/knowledge";

import { AgentOverview } from "@/components/agents/agent-overview";
import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { PublishAgentButton } from "@/components/agents/publish-agent-button";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

export default async function AgentDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string; agentId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, agentId } = await params;

  try {
    const [agent, version, knowledgeBases] = await Promise.all([
      getAgent(workspaceId, agentId),
      getLatestVersion(workspaceId, agentId),
      listKnowledgeBases(workspaceId),
    ]);

    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title={
            <span className="flex items-center gap-3">
              {agent.name}
              <AgentStatusBadge status={agent.status} />
            </span>
          }
          description={agent.description ?? "No description"}
          actions={
            <>
              <Button variant="outline" asChild>
                <Link href={`/dashboard/${workspaceId}/playground?agent=${agent.id}`}>
                  <MessageSquare />
                  Playground
                </Link>
              </Button>
              <Button variant="outline" asChild>
                <Link href={`/dashboard/${workspaceId}/agents/${agent.id}/builder`}>
                  <Pencil />
                  Open builder
                </Link>
              </Button>
              <PublishAgentButton
                workspaceId={workspaceId}
                agentId={agent.id}
                status={agent.status}
              />
            </>
          }
        />

        <AgentOverview
          workspaceId={workspaceId}
          agent={agent}
          version={version}
          knowledgeBases={knowledgeBases}
        />
      </div>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}
