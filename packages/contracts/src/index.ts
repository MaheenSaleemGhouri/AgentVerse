export { CONTRACTS_SCHEMA_VERSION } from "./version.js";

// Generated from apps/api's real OpenAPI schema (`pnpm --filter
// @agentverse/contracts run generate`, reading apps/api/openapi.json) —
// never hand-edited (CLAUDE.md §6). Regenerate and commit the diff
// whenever apps/api's routes/schemas change.
export type { components, operations, paths } from "./generated.js";

// Hand-kept (not generated): the internal provider-test route isn't
// part of the public OpenAPI surface `generated.ts` is built from, but
// its error taxonomy still needs one shared source (CLAUDE.md Rule 3).
export {
  PROVIDER_ERROR_CODES,
  type ProviderErrorCode,
  type ProviderErrorEvent,
} from "./provider-error-taxonomy.js";
