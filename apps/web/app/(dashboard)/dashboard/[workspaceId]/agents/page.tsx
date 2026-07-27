import { listAgents } from "@/lib/api/agents";

import { AgentsGrid } from "@/components/agents/agents-grid";
import { CreateAgentDialog } from "@/components/agents/create-agent-dialog";
import { PageHeader } from "@/components/patterns/page-header";

export default async function AgentsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  // Server-fetched for first paint; `AgentsGrid` seeds the TanStack
  // Query cache with it so client-side filtering and post-mutation
  // refetches take over without a loading flash (CLAUDE.md §6).
  const agents = await listAgents(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Agents"
        description="Configure instructions, model, tools, and knowledge — then publish and run."
        actions={<CreateAgentDialog workspaceId={workspaceId} />}
      />
      <AgentsGrid workspaceId={workspaceId} initialAgents={agents} />
    </div>
  );
}

export const metadata = {
  title: "Agents · AgentVerse",
};
