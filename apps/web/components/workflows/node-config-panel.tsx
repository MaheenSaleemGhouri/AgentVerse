"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Trash2 } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";

import type { Agent } from "@/lib/api/agents";
import type { Team } from "@/lib/api/teams";
import type { WorkflowEdge, WorkflowNode, WorkflowNodeType } from "@/lib/api/workflows";
import {
  agentStepConfigSchema,
  CONDITION_OPERATORS,
  humanApprovalConfigSchema,
  teamStepConfigSchema,
} from "@/lib/validation/workflow-node";
import { WORKFLOW_NODE_META } from "@/lib/workflows/node-types";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

export interface EdgeSelection {
  edge: WorkflowEdge;
  sourceNodeType: WorkflowNodeType;
}

/**
 * Renders either a node's per-type config form or an edge's branch
 * condition form — never both, since canvas selection is mutually
 * exclusive (`useWorkflowBuilderStore`). Every field edit applies
 * immediately to the canvas's local draft state via `onUpdateNode`/
 * `onUpdateEdge` rather than requiring a second, nested "save": the
 * outer builder's Save button is the one commit point that turns the
 * whole draft into a new immutable `workflow_version`, so a per-node
 * save here would just be confusing double-commit UI for no benefit.
 */
export function NodeConfigPanel({
  selectedNode,
  selectedEdge,
  agents,
  teams,
  onUpdateNode,
  onUpdateEdge,
  onDeleteNode,
  onDeleteEdge,
}: {
  selectedNode: WorkflowNode | null;
  selectedEdge: EdgeSelection | null;
  agents: Agent[];
  teams: Team[];
  onUpdateNode: (nodeId: string, patch: Partial<WorkflowNode>) => void;
  onUpdateEdge: (edgeId: string, patch: Partial<WorkflowEdge>) => void;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
}): React.JSX.Element {
  if (selectedEdge) {
    return (
      <EdgeConditionForm
        selection={selectedEdge}
        onUpdate={onUpdateEdge}
        onDelete={onDeleteEdge}
      />
    );
  }

  if (selectedNode) {
    return (
      <NodeForm
        key={selectedNode.id}
        node={selectedNode}
        agents={agents}
        teams={teams}
        onUpdate={onUpdateNode}
        onDelete={onDeleteNode}
      />
    );
  }

  return (
    <Card className="flex h-full min-h-64 flex-col items-center justify-center gap-1 p-5 text-center">
      <p className="font-medium">Nothing selected</p>
      <p className="text-sm text-muted-foreground">
        Click a node or connection on the canvas to configure it.
      </p>
    </Card>
  );
}

function NodeForm({
  node,
  agents,
  teams,
  onUpdate,
  onDelete,
}: {
  node: WorkflowNode;
  agents: Agent[];
  teams: Team[];
  onUpdate: (nodeId: string, patch: Partial<WorkflowNode>) => void;
  onDelete: (nodeId: string) => void;
}): React.JSX.Element {
  const meta = WORKFLOW_NODE_META[node.type];
  const Icon = meta.icon;

  const header = (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground"
        >
          <Icon className="size-4" />
        </span>
        <div>
          <p className="font-medium">{meta.label}</p>
          <p className="text-xs text-muted-foreground">{meta.description}</p>
        </div>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="Delete node"
        onClick={() => onDelete(node.id)}
      >
        <Trash2 />
      </Button>
    </div>
  );

  if (node.type === "agent_step") {
    return (
      <Card className="flex flex-col gap-4 p-5">
        {header}
        <AgentStepFields node={node} agents={agents} onUpdate={onUpdate} />
      </Card>
    );
  }

  if (node.type === "team_step") {
    return (
      <Card className="flex flex-col gap-4 p-5">
        {header}
        <TeamStepFields node={node} teams={teams} onUpdate={onUpdate} />
      </Card>
    );
  }

  if (node.type === "human_approval") {
    return (
      <Card className="flex flex-col gap-4 p-5">
        {header}
        <HumanApprovalFields node={node} onUpdate={onUpdate} />
      </Card>
    );
  }

  // conditional_branch / parallel_fanout: no configurable fields — the
  // node type itself is the behavior. Branch conditions live on the
  // outgoing edges, configured by selecting each connection.
  return (
    <Card className="flex flex-col gap-4 p-5">
      {header}
      <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        {node.type === "conditional_branch"
          ? "Select each outgoing connection to set which branch it routes to."
          : "Every outgoing connection runs concurrently — nothing else to configure."}
      </p>
    </Card>
  );
}

function AgentStepFields({
  node,
  agents,
  onUpdate,
}: {
  node: WorkflowNode;
  agents: Agent[];
  onUpdate: (nodeId: string, patch: Partial<WorkflowNode>) => void;
}): React.JSX.Element {
  const form = useForm({
    resolver: zodResolver(agentStepConfigSchema),
    mode: "onChange",
    defaultValues: {
      agent_id: node.agent_id ?? "",
      input_template: (node.config?.input_template as string | undefined) ?? "",
    },
  });

  React.useEffect(() => {
    const subscription = form.watch((values) => {
      if (!values.agent_id) return;
      onUpdate(node.id, {
        agent_id: values.agent_id,
        config: { ...node.config, input_template: values.input_template || undefined },
      });
    });
    return () => subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-subscribes on node identity, matching agent-config-panel's watch pattern
  }, [form, node.id]);

  return (
    <Form {...form}>
      <form className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="agent_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Agent</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Choose a published agent" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {agents.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="input_template"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Input (optional)</FormLabel>
              <FormControl>
                <Textarea
                  rows={3}
                  placeholder="{{trigger.input}}"
                  className="font-mono text-sm"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  );
}

function TeamStepFields({
  node,
  teams,
  onUpdate,
}: {
  node: WorkflowNode;
  teams: Team[];
  onUpdate: (nodeId: string, patch: Partial<WorkflowNode>) => void;
}): React.JSX.Element {
  const form = useForm({
    resolver: zodResolver(teamStepConfigSchema),
    mode: "onChange",
    defaultValues: {
      team_id: node.team_id ?? "",
      input_template: (node.config?.input_template as string | undefined) ?? "",
    },
  });

  React.useEffect(() => {
    const subscription = form.watch((values) => {
      if (!values.team_id) return;
      onUpdate(node.id, {
        team_id: values.team_id,
        config: { ...node.config, input_template: values.input_template || undefined },
      });
    });
    return () => subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, node.id]);

  return (
    <Form {...form}>
      <form className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="team_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Team</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Choose a team" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {teams.map((team) => (
                    <SelectItem key={team.id} value={team.id}>
                      {team.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="input_template"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Input (optional)</FormLabel>
              <FormControl>
                <Textarea
                  rows={3}
                  placeholder="{{trigger.input}}"
                  className="font-mono text-sm"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  );
}

function HumanApprovalFields({
  node,
  onUpdate,
}: {
  node: WorkflowNode;
  onUpdate: (nodeId: string, patch: Partial<WorkflowNode>) => void;
}): React.JSX.Element {
  const form = useForm({
    resolver: zodResolver(humanApprovalConfigSchema),
    mode: "onChange",
    defaultValues: { message: (node.config?.message as string | undefined) ?? "" },
  });

  React.useEffect(() => {
    const subscription = form.watch((values) => {
      onUpdate(node.id, { config: { ...node.config, message: values.message } });
    });
    return () => subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, node.id]);

  return (
    <Form {...form}>
      <form className="flex flex-col gap-4">
        <FormField
          control={form.control}
          name="message"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Message for the reviewer</FormLabel>
              <FormControl>
                <Textarea rows={4} placeholder="What are they approving?" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  );
}

function EdgeConditionForm({
  selection,
  onUpdate,
  onDelete,
}: {
  selection: EdgeSelection;
  onUpdate: (edgeId: string, patch: Partial<WorkflowEdge>) => void;
  onDelete: (edgeId: string) => void;
}): React.JSX.Element {
  const { edge, sourceNodeType } = selection;

  const header = (
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="font-medium">Connection</p>
        <p className="text-xs text-muted-foreground">
          {sourceNodeType === "conditional_branch"
            ? "Fires when its condition matches, evaluated in branch order."
            : "This connection always fires."}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="Delete connection"
        onClick={() => onDelete(edge.id)}
      >
        <Trash2 />
      </Button>
    </div>
  );

  if (sourceNodeType !== "conditional_branch") {
    return (
      <Card className="flex flex-col gap-4 p-5">
        {header}
      </Card>
    );
  }

  const isDefault = edge.condition == null;

  return (
    <Card className="flex flex-col gap-4 p-5">
      {header}
      <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
        <div>
          <p className="text-sm font-medium">Default / else branch</p>
          <p className="text-xs text-muted-foreground">
            Always matches — used when no other branch does.
          </p>
        </div>
        <Switch
          checked={isDefault}
          onCheckedChange={(next) =>
            onUpdate(edge.id, {
              condition: next ? null : { field: "", operator: "equals", value: "" },
            })
          }
          aria-label="Default branch"
        />
      </div>

      {!isDefault && (
        <div className="flex flex-col gap-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor={`cond-field-${edge.id}`}>
              Field
            </label>
            <Input
              id={`cond-field-${edge.id}`}
              placeholder="category"
              value={(edge.condition?.field as string | undefined) ?? ""}
              onChange={(event) =>
                onUpdate(edge.id, {
                  condition: { ...edge.condition, field: event.target.value, operator: (edge.condition?.operator as string) ?? "equals", value: (edge.condition?.value as string) ?? "" },
                })
              }
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor={`cond-op-${edge.id}`}>
              Operator
            </label>
            <Select
              value={(edge.condition?.operator as string) ?? "equals"}
              onValueChange={(value) =>
                onUpdate(edge.id, { condition: { ...edge.condition, operator: value } })
              }
            >
              <SelectTrigger className="w-full" id={`cond-op-${edge.id}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CONDITION_OPERATORS.map((op) => (
                  <SelectItem key={op} value={op}>
                    {op.replace("_", " ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor={`cond-value-${edge.id}`}>
              Value
            </label>
            <Input
              id={`cond-value-${edge.id}`}
              placeholder="refund"
              value={(edge.condition?.value as string | undefined) ?? ""}
              onChange={(event) =>
                onUpdate(edge.id, { condition: { ...edge.condition, value: event.target.value } })
              }
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor={`cond-order-${edge.id}`}>
              Branch order
            </label>
            <Input
              id={`cond-order-${edge.id}`}
              type="number"
              min={0}
              value={edge.branch_order ?? 0}
              onChange={(event) =>
                onUpdate(edge.id, { branch_order: Number(event.target.value) })
              }
            />
            <p className="text-xs text-muted-foreground">
              Lower numbers are evaluated first.
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}
