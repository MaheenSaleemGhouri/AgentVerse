export { CONTRACTS_SCHEMA_VERSION } from "./version.js";

// Generated from apps/api's real OpenAPI schema (`pnpm --filter
// @agentverse/contracts run generate`, reading apps/api/openapi.json) —
// never hand-edited (CLAUDE.md §6). Regenerate and commit the diff
// whenever apps/api's routes/schemas change.
export type { components, operations, paths } from "./generated.js";
