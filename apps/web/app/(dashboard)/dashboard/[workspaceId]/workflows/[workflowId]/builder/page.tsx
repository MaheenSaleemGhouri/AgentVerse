import { headers } from "next/headers";
import { notFound } from "next/navigation";

import { listAgents } from "@/lib/api/agents";
import { auth } from "@/lib/auth";
import { ApiError } from "@/lib/api/client";
import { listTeams } from "@/lib/api/teams";
import { getLatestWorkflowVersion, getWorkflow } from "@/lib/api/workflows";

import { WorkflowBuilder } from "@/components/workflows/workflow-builder";

export default async function WorkflowBuilderPage({
  params,
}: {
  params: Promise<{ workspaceId: string; workflowId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, workflowId } = await params;

  const workflow = await getWorkflow(workspaceId, workflowId).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  });
  if (!workflow) {
    notFound();
  }

  const version = await getLatestWorkflowVersion(workspaceId, workflowId);
  if (!version) {
    // Every workflow is created with a first (empty) version in the same
    // transaction (create_workflow.py) — reaching here means the
    // workflow is in a state this UI doesn't support editing.
    notFound();
  }

  // Fetched here rather than inside the canvas so the agent/team step
  // config forms render their pickers complete on first paint instead of
  // popping in.
  const [agents, teams, session] = await Promise.all([
    listAgents(workspaceId),
    listTeams(workspaceId),
    auth.api.getSession({ headers: await headers() }),
  ]);

  return (
    <WorkflowBuilder
      workspaceId={workspaceId}
      workflow={workflow}
      version={version}
      agents={agents}
      teams={teams}
      displayName={session?.user.name ?? session?.user.email ?? "Someone"}
    />
  );
}
