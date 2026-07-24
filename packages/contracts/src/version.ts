/**
 * Contract schema version for this package's generated types.
 *
 * Bumped whenever `apps/api`'s OpenAPI schema changes in a way that
 * affects generated output. Consumers (apps/web) can assert against
 * this at build time to catch a stale `pnpm --filter contracts build`
 * before it becomes a runtime type mismatch.
 */
export const CONTRACTS_SCHEMA_VERSION = "0.1.0-alpha" as const;
