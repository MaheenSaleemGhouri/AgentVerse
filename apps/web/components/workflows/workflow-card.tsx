import Link from "next/link";
import * as React from "react";

import type { Workflow } from "@/lib/api/workflows";
import { formatRelativeTime } from "@/lib/format";
import { WORKFLOW_NODE_META } from "@/lib/workflows/node-types";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { Card } from "@/components/ui/card";

const WorkflowIcon = WORKFLOW_NODE_META.agent_step.icon;

/**
 * `AgentStatusBadge` is reused as-is rather than a duplicated
 * `WorkflowStatusBadge`: `workflows.status` uses the identical
 * draft/active/archived vocabulary by design (docs/adr/0016), and a
 * second color map would just be Rule 3 duplication of the same tokens.
 */
export function WorkflowCard({
  workspaceId,
  workflow,
}: {
  workspaceId: string;
  workflow: Workflow;
}): React.JSX.Element {
  const detailHref = `/dashboard/${workspaceId}/workflows/${workflow.id}/builder`;

  return (
    <Card className="group relative gap-0 p-5 transition-[transform,border-color] duration-150 hover:-translate-y-px hover:border-primary/50 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
        >
          <WorkflowIcon className="size-4.5" />
        </span>

        <div className="min-w-0 flex-1">
          <Link
            href={detailHref}
            className="font-medium after:absolute after:inset-0 after:content-[''] hover:underline"
          >
            {workflow.name}
          </Link>
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
            {workflow.description ?? "No description"}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <AgentStatusBadge status={workflow.status} />
        <span className="ml-auto text-xs text-muted-foreground">
          Updated {formatRelativeTime(workflow.updated_at)}
        </span>
      </div>
    </Card>
  );
}
