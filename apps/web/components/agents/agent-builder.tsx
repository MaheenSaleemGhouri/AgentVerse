"use client";

import { CloudUpload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { publishAgentAction } from "@/lib/api/actions";
import type { Agent, AgentVersion } from "@/lib/api/agents";
import { useAgentBuilderStore } from "@/lib/stores/agent-builder-store";

import { AgentBuilderCanvas } from "@/components/agents/agent-builder-canvas";
import { AgentConfigPanel } from "@/components/agents/agent-config-panel";
import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { RunTestTrigger } from "@/components/agents/run-test-trigger";
import { Button } from "@/components/ui/button";

export function AgentBuilder({
  workspaceId,
  agent: initialAgent,
  version: initialVersion,
}: {
  workspaceId: string;
  agent: Agent;
  version: AgentVersion;
}): React.JSX.Element {
  const router = useRouter();
  const [agent, setAgent] = useState(initialAgent);
  const [version, setVersion] = useState(initialVersion);
  const [isPublishing, setIsPublishing] = useState(false);
  const resetBuilderStore = useAgentBuilderStore((s) => s.reset);

  // Ephemeral builder-session state (active tab, dirty flag) never
  // survives a navigation away from this agent's builder.
  useEffect(() => resetBuilderStore, [resetBuilderStore]);

  const isPublished = agent.published_version_id === version.id;

  async function handlePublish(): Promise<void> {
    setIsPublishing(true);
    try {
      const published = await publishAgentAction(workspaceId, agent.id);
      setAgent(published);
      toast.success("Agent published");
      router.refresh();
    } catch {
      toast.error("Could not publish — try again.");
    } finally {
      setIsPublishing(false);
    }
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{agent.name}</h1>
          <AgentStatusBadge status={agent.status} />
          <span className="text-sm text-muted-foreground">v{version.version_number}</span>
        </div>
        <Button onClick={() => void handlePublish()} disabled={isPublishing || isPublished}>
          <CloudUpload />
          {isPublishing ? "Publishing…" : isPublished ? "Published" : "Publish"}
        </Button>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-4">
          <AgentBuilderCanvas agent={agent} version={version} />
          <RunTestTrigger workspaceId={workspaceId} agentId={agent.id} canRun={agent.status === "active"} />
        </div>
        <AgentConfigPanel
          workspaceId={workspaceId}
          agentId={agent.id}
          version={version}
          onSaved={setVersion}
        />
      </div>
    </div>
  );
}
