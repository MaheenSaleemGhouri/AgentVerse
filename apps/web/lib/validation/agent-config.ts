import { z } from "zod";

/**
 * Mirrors apps/api's `UpdateAgentVersionRequest` field constraints
 * exactly (interface/schemas/agents.py) so a form-side rejection and a
 * server-side rejection never disagree.
 */
export const agentConfigSchema = z.object({
  model: z.string().min(1).max(64),
  system_instructions: z.string().min(1).max(8000),
  temperature: z.number().min(0).max(2).nullable(),
  max_output_tokens: z.number().int().min(1).max(32000).nullable(),
  tools: z.array(z.string()).max(20),
  knowledge_base_ids: z.array(z.string()).max(10),
});

export type AgentConfigFormValues = z.infer<typeof agentConfigSchema>;

/**
 * The fixed, trusted built-in tool set apps/worker's `resolve_tools`
 * dispatches (agents/builtin_tools.py) — Phase 6's central
 * tool-execution boundary will replace this with a dynamic,
 * workspace-scoped catalog. Kept in sync by hand until then.
 */
export const BUILTIN_TOOLS = [
  { id: "get_current_time", label: "Current time", description: "Returns the current UTC time." },
  {
    id: "calculator",
    label: "Calculator",
    description: "Evaluates a basic arithmetic expression.",
  },
] as const;

export const MODEL_OPTIONS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"] as const;
