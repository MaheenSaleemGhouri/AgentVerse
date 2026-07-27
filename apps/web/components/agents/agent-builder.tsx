"use client";

import { ArrowLeft, CircleDot } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import * as React from "react";

import type { Agent, AgentVersion } from "@/lib/api/agents";
import type { KnowledgeBase } from "@/lib/api/knowledge";
import { useAgentBuilderStore } from "@/lib/stores/agent-builder-store";

import { AgentConfigPanel } from "@/components/agents/agent-config-panel";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * The canvas is the only surface pulling in framer-motion, so it is
 * loaded on demand — the dashboard, knowledge, and settings routes must
 * not pay for animation weight they never render (CLAUDE.md §17).
 *
 * The placeholder matches the canvas's real height so opening the
 * builder does not shift layout when it arrives.
 */
const AgentBuilderCanvas = dynamic(
  () => import("@/components/agents/agent-builder-canvas").then((m) => m.AgentBuilderCanvas),
  { loading: () => <Skeleton className="min-h-[440px] rounded-xl" /> }
);
import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { PublishAgentButton } from "@/components/agents/publish-agent-button";
import { RunTestTrigger } from "@/components/agents/run-test-trigger";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function AgentBuilder({
  workspaceId,
  agent,
  version: initialVersion,
  knowledgeBases,
}: {
  workspaceId: string;
  agent: Agent;
  version: AgentVersion;
  knowledgeBases: KnowledgeBase[];
}): React.JSX.Element {
  const [version, setVersion] = React.useState(initialVersion);
  const activeTab = useAgentBuilderStore((s) => s.activeTab);
  const isDirty = useAgentBuilderStore((s) => s.isDirty);
  const resetBuilderStore = useAgentBuilderStore((s) => s.reset);

  // Ephemeral builder-session state (active tab, dirty flag) never
  // survives a navigation away from this agent's builder.
  React.useEffect(() => resetBuilderStore, [resetBuilderStore]);

  // Warn before losing unsaved edits — a version that was never saved is
  // unrecoverable, unlike almost everything else in the product.
  React.useEffect(() => {
    if (!isDirty) return;
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="icon-sm" asChild aria-label="Back to agent">
          <Link href={`/dashboard/${workspaceId}/agents/${agent.id}`}>
            <ArrowLeft />
          </Link>
        </Button>

        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{agent.name}</h1>
            <AgentStatusBadge status={agent.status} />
            <Badge variant="outline" className="font-mono text-xs">
              v{version.version_number}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Saving creates a new version — published versions are never edited in place.
          </p>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {isDirty && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-warning">
              <CircleDot className="size-3" aria-hidden="true" />
              Unsaved changes
            </span>
          )}
          <Separator orientation="vertical" className="h-6" />
          <PublishAgentButton
            workspaceId={workspaceId}
            agentId={agent.id}
            status={agent.status}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.1fr_minmax(0,440px)]">
        <div className="flex min-w-0 flex-col gap-5">
          <AgentBuilderCanvas
            agent={agent}
            version={version}
            knowledgeBases={knowledgeBases}
            activeTab={activeTab}
          />
          <RunTestTrigger
            workspaceId={workspaceId}
            agentId={agent.id}
            canRun={agent.status === "active"}
          />
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
