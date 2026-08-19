"use client";

import { Search, Workflow as WorkflowIcon } from "lucide-react";
import * as React from "react";

import type { Workflow } from "@/lib/api/workflows";
import { useWorkflows } from "@/lib/queries/workflows";

import { CreateWorkflowDialog } from "@/components/workflows/create-workflow-dialog";
import { WorkflowCard } from "@/components/workflows/workflow-card";
import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Search is local UI state over the already-fetched list, same rationale
 * as `AgentsGrid` — the full list is already in the TanStack Query
 * cache, so re-filtering it client-side is instant.
 */
export function WorkflowsGrid({
  workspaceId,
  initialWorkflows,
}: {
  workspaceId: string;
  initialWorkflows: Workflow[];
}): React.JSX.Element {
  const { data: workflows, isLoading, isError, refetch } = useWorkflows(
    workspaceId,
    initialWorkflows
  );
  const [query, setQuery] = React.useState("");

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return workflows ?? [];
    return (workflows ?? []).filter(
      (workflow: Workflow) =>
        workflow.name.toLowerCase().includes(needle) ||
        (workflow.description ?? "").toLowerCase().includes(needle)
    );
  }, [workflows, query]);

  if (isError) {
    return (
      <ErrorState
        title="Could not load workflows"
        description="The workflows API did not respond. Your session may have expired."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading && !workflows) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-32 rounded-xl" />
        ))}
      </div>
    );
  }

  if ((workflows ?? []).length === 0) {
    return (
      <EmptyState
        icon={WorkflowIcon}
        mascot="waving"
        title="No workflows yet"
        description="A workflow chains agent and team steps on a DAG canvas, with branching and human approval. Create one to get started."
        action={<CreateWorkflowDialog workspaceId={workspaceId} />}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search workflows…"
          aria-label="Search workflows"
          className="pl-9"
        />
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No workflows match"
          description="Try a different search term."
          action={
            <Button variant="outline" onClick={() => setQuery("")}>
              Clear search
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((workflow: Workflow) => (
            <WorkflowCard key={workflow.id} workspaceId={workspaceId} workflow={workflow} />
          ))}
        </div>
      )}
    </div>
  );
}
