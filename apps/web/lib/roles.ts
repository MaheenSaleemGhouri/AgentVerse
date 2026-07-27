import type { Role } from "@/lib/api/workspaces";

/**
 * The workspace role hierarchy, defined once.
 *
 * Mirrors the backend's `owner > admin > member > viewer` ordering
 * (CLAUDE.md §7). Duplicating these strings per component is how a
 * permission check drifts from what the API actually enforces, so every
 * consumer reads them from here.
 */
export const ROLE_ORDER: Record<Role, number> = {
  owner: 3,
  admin: 2,
  member: 1,
  viewer: 0,
};

export const ASSIGNABLE_ROLES: readonly Role[] = ["admin", "member", "viewer"];

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  owner: "Full control, including deleting the workspace and transferring ownership.",
  admin: "Manage members, agents, knowledge, and API keys.",
  member: "Create and run agents, and manage knowledge bases.",
  viewer: "Read-only access to agents, runs, and knowledge.",
};

/** Whether `actor` outranks `target` — the rule behind every row action. */
export function outranks(actor: Role, target: Role): boolean {
  return ROLE_ORDER[actor] > ROLE_ORDER[target];
}
