import { GitBranch, ShieldQuestion, Split, Workflow } from "lucide-react";

import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { Card } from "@/components/ui/card";

/**
 * Workflow builder shell.
 *
 * The canvas itself is not stubbed with draggable fake nodes — a graph
 * editor that cannot save is a worse experience than an honest one. What
 * is shown is the node vocabulary the backend will support, so the shape
 * of the feature is legible before it exists.
 */
const NODE_TYPES = [
  {
    icon: Workflow,
    label: "Agent step",
    description: "Run a published agent and pass its output downstream.",
  },
  {
    icon: Split,
    label: "Conditional branch",
    description: "Route to different steps based on the previous step's result.",
  },
  {
    icon: ShieldQuestion,
    label: "Human approval",
    description: "Pause durably until a person approves or rejects, then resume.",
  },
  {
    icon: GitBranch,
    label: "Parallel fan-out",
    description: "Run several steps concurrently and join their results.",
  },
];

export default function WorkflowsPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Workflows"
        description="Chain agents into multi-step processes with branching and human approval."
      />

      <IntegrationPending feature="workflows">
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">Planned node types</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {NODE_TYPES.map((node) => {
              const Icon = node.icon;
              return (
                <Card key={node.label} className="gap-2 p-5">
                  <span
                    aria-hidden="true"
                    className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground"
                  >
                    <Icon className="size-4.5" />
                  </span>
                  <p className="mt-1 font-medium">{node.label}</p>
                  <p className="text-sm text-muted-foreground">{node.description}</p>
                </Card>
              );
            })}
          </div>
        </section>
      </IntegrationPending>
    </div>
  );
}

export const metadata = {
  title: "Workflows · AgentVerse",
};
