import { notFound } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { getWorkflow, getWorkflowVersion } from "@/lib/api/workflows";

import { WorkflowRunStatus } from "@/components/workflows/workflow-run-status";
import { PageHeader } from "@/components/patterns/page-header";

export default async function WorkflowRunPage({
  params,
}: {
  params: Promise<{ workspaceId: string; workflowId: string; runId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, workflowId, runId } = await params;

  const workflow = await getWorkflow(workspaceId, workflowId).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  });
  if (!workflow) {
    notFound();
  }

  // A run always executes the published version at the time it was
  // triggered — `WorkflowRunResponse` does not carry the exact version
  // id it ran against, so the currently-published version is the best
  // available node lookup. If the workflow has since been republished
  // with a different graph, an older run's step labels degrade to the
  // raw node id rather than crashing (WorkflowRunStatus's fallback).
  const nodesById = new Map(
    workflow.published_version_id
      ? (await getWorkflowVersion(workspaceId, workflowId, workflow.published_version_id)).nodes.map(
          (node) => [node.id, node] as const
        )
      : []
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={`Run ${runId.slice(0, 8)}`} description={workflow.name} />
      <WorkflowRunStatus
        workspaceId={workspaceId}
        workflowId={workflowId}
        runId={runId}
        nodesById={nodesById}
      />
    </div>
  );
}

export const metadata = {
  title: "Workflow run · AgentVerse",
};
