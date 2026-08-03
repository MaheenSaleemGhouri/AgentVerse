import type { Role } from "@/lib/api/workspaces";

/**
 * The workspace role hierarchy, defined once.
 *
 * Mirrors the backend's `owner > admin > manager > developer > analyst >
 * member > viewer` ordering (CLAUDE.md §7). Duplicating these strings per
 * component is how a permission check drifts from what the API actually
 * enforces, so every consumer reads them from here.
 *
 * These numbers are display/ordering only — they gate nothing. The server
 * is the sole authority on what a role may do, and the per-permission
 * detail lives in its matrix, served by
 * `GET /api/v1/workspaces/{id}/roles/builtin` rather than mirrored here,
 * so the UI can never drift from enforcement.
 */
export const ROLE_ORDER: Record<Role, number> = {
  owner: 6,
  admin: 5,
  manager: 4,
  developer: 3,
  analyst: 2,
  member: 1,
  viewer: 0,
};

/**
 * Roles an admin can hand out. `owner` is absent deliberately: ownership
 * moves through the explicit transfer flow, which enforces that a
 * workspace never ends up with zero owners.
 */
export const ASSIGNABLE_ROLES: readonly Role[] = [
  "admin",
  "manager",
  "developer",
  "analyst",
  "member",
  "viewer",
];

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  owner: "Full control, including deleting the workspace and transferring ownership.",
  admin: "Everything a manager can do, plus billing.",
  manager: "Manage members, roles, and workspace settings.",
  developer: "Build and delete agents, install MCP integrations, and manage API keys.",
  analyst: "Read analytics and audit logs, and export both. No authoring rights.",
  member: "Create and run agents, and manage knowledge bases.",
  viewer: "Read-only access to agents, runs, and knowledge.",
};

/** Whether `actor` outranks `target` — the rule behind every row action. */
export function outranks(actor: Role, target: Role): boolean {
  return ROLE_ORDER[actor] > ROLE_ORDER[target];
}
