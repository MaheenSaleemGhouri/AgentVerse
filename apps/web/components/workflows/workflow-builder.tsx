"use client";

import { ArrowLeft, CircleDot, Save } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { Team } from "@/lib/api/teams";
import type { Workflow, WorkflowVersion } from "@/lib/api/workflows";
import { useWorkflowCollab } from "@/lib/hooks/useWorkflowCollab";
import { useCreateWorkflowVersion } from "@/lib/queries/workflows";
import { useWorkflowBuilderStore } from "@/lib/stores/workflow-builder-store";

import { PresenceAvatars } from "@/components/workflows/presence-avatars";
import { PublishWorkflowButton } from "@/components/workflows/publish-workflow-button";
import { RunWorkflowTrigger } from "@/components/workflows/run-workflow-trigger";
import { ShareWorkflowButton } from "@/components/workflows/share-workflow-button";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * The canvas is the only surface pulling in @xyflow/react (and its
 * required stylesheet), so it is loaded on demand — the dashboard,
 * knowledge, and settings routes must not pay for canvas weight they
 * never render (CLAUDE.md §17, mirroring `AgentBuilder`'s
 * `next/dynamic` split for `AgentBuilderCanvas`).
 */
const WorkflowCanvas = dynamic(
  () => import("@/components/workflows/workflow-canvas").then((m) => m.WorkflowCanvas),
  { loading: () => <Skeleton className="min-h-[520px] rounded-xl" />, ssr: false }
);

export function WorkflowBuilder({
  workspaceId,
  workflow,
  version,
  agents,
  teams,
  displayName,
}: {
  workspaceId: string;
  workflow: Workflow;
  version: WorkflowVersion;
  agents: Agent[];
  teams: Team[];
  displayName: string;
}): React.JSX.Element {
  const [draftNodes, setDraftNodes] = React.useState(version.nodes);
  const [draftEdges, setDraftEdges] = React.useState(version.edges);
  const [latestVersion, setLatestVersion] = React.useState(version);
  const isDirty = useWorkflowBuilderStore((s) => s.isDirty);
  const setDirty = useWorkflowBuilderStore((s) => s.setDirty);
  const resetBuilderStore = useWorkflowBuilderStore((s) => s.reset);
  const createVersion = useCreateWorkflowVersion(workspaceId, workflow.id);

  const collab = useWorkflowCollab(workspaceId, workflow.id, displayName);

  React.useEffect(() => resetBuilderStore, [resetBuilderStore]);

  React.useEffect(() => {
    if (!isDirty) return;
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  async function handleSave(): Promise<void> {
    const saved = await createVersion.mutateAsync({ nodes: draftNodes, edges: draftEdges });
    setLatestVersion(saved);
    setDirty(false);
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="icon-sm" asChild aria-label="Back to workflows">
          <Link href={`/dashboard/${workspaceId}/workflows`}>
            <ArrowLeft />
          </Link>
        </Button>

        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">{workflow.name}</h1>
            <span className="rounded-full border border-border px-2 py-0.5 font-mono text-xs text-muted-foreground">
              v{latestVersion.version_number}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Saving creates a new version — published versions are never edited in place.
          </p>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <PresenceAvatars presence={collab.presence} />
          {isDirty && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-warning">
              <CircleDot className="size-3" aria-hidden="true" />
              Unsaved changes
            </span>
          )}
          <Separator orientation="vertical" className="h-6" />
          <Button
            variant="outline"
            onClick={() => void handleSave()}
            disabled={!isDirty || createVersion.isPending}
          >
            <Save />
            {createVersion.isPending ? "Saving…" : "Save"}
          </Button>
          <ShareWorkflowButton workspaceId={workspaceId} workflowId={workflow.id} />
          <PublishWorkflowButton
            workspaceId={workspaceId}
            workflowId={workflow.id}
            status={workflow.status}
            latestVersionId={latestVersion.id}
            publishedVersionId={workflow.published_version_id}
          />
        </div>
      </div>

      <WorkflowCanvas
        initialNodes={version.nodes}
        initialEdges={version.edges}
        agents={agents}
        teams={teams}
        onGraphChange={(nodes, edges) => {
          setDraftNodes(nodes);
          setDraftEdges(edges);
        }}
        remoteEvent={collab.lastEvent}
        onLocalEvent={collab.send}
      />

      <RunWorkflowTrigger
        workspaceId={workspaceId}
        workflowId={workflow.id}
        canRun={workflow.status === "active"}
        nodes={latestVersion.nodes}
      />
    </div>
  );
}
