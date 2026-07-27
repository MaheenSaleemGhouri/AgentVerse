import { describe, expect, it } from "vitest";

import { agentConfigSchema } from "./agent-config";

const VALID = {
  model: "gpt-4o-mini",
  system_instructions: "You are a helpful assistant.",
  temperature: 0.7,
  max_output_tokens: 1000,
  tools: ["calculator"],
  // Required by the schema since Phase 5 attached knowledge bases to a
  // version. Omitting it made every "accepts a valid config" case fail
  // on a missing field rather than on what it was testing.
  knowledge_base_ids: [],
};

describe("agentConfigSchema", () => {
  it("accepts a fully populated valid config", () => {
    const result = agentConfigSchema.safeParse(VALID);
    expect(result.success).toBe(true);
  });

  it("accepts null temperature and max_output_tokens (both optional server-side)", () => {
    const result = agentConfigSchema.safeParse({
      ...VALID,
      temperature: null,
      max_output_tokens: null,
    });
    expect(result.success).toBe(true);
  });

  it("rejects empty system_instructions — mirrors apps/api's min_length=1", () => {
    const result = agentConfigSchema.safeParse({ ...VALID, system_instructions: "" });
    expect(result.success).toBe(false);
  });

  it("rejects system_instructions over 8000 chars — mirrors apps/api's prompt-injection cap", () => {
    const result = agentConfigSchema.safeParse({
      ...VALID,
      system_instructions: "x".repeat(8001),
    });
    expect(result.success).toBe(false);
  });

  it("rejects temperature outside [0, 2] — mirrors apps/api's ge/le constraint", () => {
    expect(agentConfigSchema.safeParse({ ...VALID, temperature: 2.1 }).success).toBe(false);
    expect(agentConfigSchema.safeParse({ ...VALID, temperature: -0.1 }).success).toBe(false);
  });

  it("rejects more than 20 tools — mirrors apps/api's max_length=20", () => {
    const result = agentConfigSchema.safeParse({
      ...VALID,
      tools: Array.from({ length: 21 }, (_, i) => `tool-${i}`),
    });
    expect(result.success).toBe(false);
  });
});
