import { listWorkflows } from "@/lib/api/workflows";

import { CreateWorkflowDialog } from "@/components/workflows/create-workflow-dialog";
import { WorkflowsGrid } from "@/components/workflows/workflows-grid";
import { PageHeader } from "@/components/patterns/page-header";

export default async function WorkflowsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  // Server-fetched for first paint; `WorkflowsGrid` seeds the TanStack
  // Query cache with it so client-side search and post-mutation
  // refetches take over without a loading flash (CLAUDE.md §6).
  const workflows = await listWorkflows(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Workflows"
        description="Chain agents into multi-step processes with branching and human approval."
        actions={<CreateWorkflowDialog workspaceId={workspaceId} />}
      />
      <WorkflowsGrid workspaceId={workspaceId} initialWorkflows={workflows} />
    </div>
  );
}

export const metadata = {
  title: "Workflows · AgentVerse",
};
