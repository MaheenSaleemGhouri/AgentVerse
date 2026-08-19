import { GitBranch, ShieldQuestion, Split, Users2, Workflow as WorkflowIcon } from "lucide-react";

import type { WorkflowNodeType } from "@/lib/api/workflows";

/**
 * The one node-vocabulary registry — palette, canvas node rendering, and
 * the run-trace status list all read from here, so a label or icon is
 * never redefined per consumer (Rule 3). Mirrors the four-plus-one
 * types the placeholder page named before this feature had a backend.
 */
export const WORKFLOW_NODE_META: Record<
  WorkflowNodeType,
  { label: string; description: string; icon: React.ComponentType<{ className?: string }> }
> = {
  agent_step: {
    label: "Agent step",
    description: "Run a published agent and pass its output downstream.",
    icon: WorkflowIcon,
  },
  team_step: {
    label: "Team step",
    description: "Run a multi-agent team and pass its output downstream.",
    icon: Users2,
  },
  conditional_branch: {
    label: "Conditional branch",
    description: "Route to different steps based on the previous step's result.",
    icon: Split,
  },
  human_approval: {
    label: "Human approval",
    description: "Pause durably until a person approves or rejects, then resume.",
    icon: ShieldQuestion,
  },
  parallel_fanout: {
    label: "Parallel fan-out",
    description: "Run several steps concurrently and join their results.",
    icon: GitBranch,
  },
};
