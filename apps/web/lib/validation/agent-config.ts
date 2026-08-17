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

/**
 * Provider-grouped catalog. Mirrors the provider-prefix convention
 * `apps/worker`'s `resolve_model()` and `packages/python-shared`'s
 * `cost_accounting.py` both key off (Phase 11): no `/` means OpenAI,
 * resolved unchanged exactly as before; an `anthropic/` prefix routes
 * through the worker's LiteLLM extension. Every model string here MUST
 * have a matching `MODEL_PRICING`/`MODEL_CONTEXT_WINDOWS` entry in
 * `cost_accounting.py`, or selecting it crashes the run.
 */
export const MODEL_CATALOG = [
  { provider: "OpenAI", models: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"] },
  {
    provider: "Anthropic",
    models: ["anthropic/claude-haiku-4-5", "anthropic/claude-sonnet-5"],
  },
] as const;

/** Flat list derived from `MODEL_CATALOG` — existing consumers that only need "is this a valid model string" keep working unchanged. */
export const MODEL_OPTIONS = MODEL_CATALOG.flatMap((group) => group.models);
