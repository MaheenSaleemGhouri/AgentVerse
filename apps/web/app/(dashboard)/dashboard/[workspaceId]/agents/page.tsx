import { Bot } from "lucide-react";

import { listAgents } from "@/lib/api/agents";

import { AgentCard } from "@/components/agents/agent-card";
import { CreateAgentDialog } from "@/components/agents/create-agent-dialog";

export default async function AgentsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const agents = await listAgents(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Build a single agent with tools, then run it and watch it work.
          </p>
        </div>
        <CreateAgentDialog workspaceId={workspaceId} />
      </div>

      {agents.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
            <Bot className="size-6" />
          </span>
          <div>
            <p className="font-medium">No agents yet</p>
            <p className="text-sm text-muted-foreground">
              Create your first agent to reach a working run in minutes.
            </p>
          </div>
          <CreateAgentDialog workspaceId={workspaceId} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <AgentCard key={agent.id} workspaceId={workspaceId} agent={agent} />
          ))}
        </div>
      )}
    </div>
  );
}
