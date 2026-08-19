import { z } from "zod";

/**
 * One schema per `WorkflowNodeType`, validating the shape stored in
 * `workflow_nodes.config` (JSONB — the API stores flexibility, this is
 * the application-layer shape enforcement, CLAUDE.md §8). Mirrors
 * `apps/worker/src/agentverse_worker/workflows/graph_runtime.py`'s
 * `resolve_input_template`/`evaluate_condition` exactly: a form-side
 * rejection and the worker's actual runtime behavior must never
 * disagree about what a placeholder or operator means.
 */

const inputTemplateField = z
  .string()
  .max(4000)
  .optional()
  .describe("{{trigger.input}} substitutes the run's trigger input; {{nodes.<id>.output}} substitutes a prior node's output.");

export const agentStepConfigSchema = z.object({
  agent_id: z.string().min(1, "Choose an agent"),
  input_template: inputTemplateField,
});
export type AgentStepConfigValues = z.infer<typeof agentStepConfigSchema>;

export const teamStepConfigSchema = z.object({
  team_id: z.string().min(1, "Choose a team"),
  input_template: inputTemplateField,
});
export type TeamStepConfigValues = z.infer<typeof teamStepConfigSchema>;

export const humanApprovalConfigSchema = z.object({
  message: z.string().min(1, "Reviewers need to know what they're approving").max(2000),
});
export type HumanApprovalConfigValues = z.infer<typeof humanApprovalConfigSchema>;

/** No configurable fields — the node type itself is the behavior. */
export const conditionalBranchConfigSchema = z.object({});
export const parallelFanoutConfigSchema = z.object({});

/** `apps/worker`'s `evaluate_condition` — the only operators it understands. */
export const CONDITION_OPERATORS = ["equals", "not_equals", "contains"] as const;

export const edgeConditionSchema = z
  .object({
    field: z.string().min(1, "Field is required"),
    operator: z.enum(CONDITION_OPERATORS),
    value: z.string(),
  })
  .nullable();
export type EdgeConditionValues = z.infer<typeof edgeConditionSchema>;
