import { listAgents } from "@/lib/api/agents";

import { PageHeader } from "@/components/patterns/page-header";
import { Playground } from "@/components/playground/playground";

export default async function PlaygroundPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ agent?: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const { agent: preselectedAgentId } = await searchParams;
  const agents = await listAgents(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Playground"
        description="Run a published agent and watch every step of its execution stream live."
      />
      <Playground
        workspaceId={workspaceId}
        agents={agents}
        preselectedAgentId={preselectedAgentId ?? null}
      />
    </div>
  );
}

export const metadata = {
  title: "Playground · AgentVerse",
};
