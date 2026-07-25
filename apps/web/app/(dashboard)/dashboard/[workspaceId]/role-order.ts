import type { Role } from "@/lib/api/workspaces";

// Mirrors apps/api/src/agentverse_api/auth_service/domain/role.py's
// hierarchy — UI-only gating (which controls to *show*); the server
// enforces the real check regardless (ADR-0004), this just avoids
// flashing a control the user's next click would get a 403 from.
const RANK: Record<Role, number> = { owner: 3, admin: 2, member: 1, viewer: 0 };

export function roleSatisfies(actual: Role, minimum: Role): boolean {
  return RANK[actual] >= RANK[minimum];
}

export const ALL_ROLES: Role[] = ["owner", "admin", "member", "viewer"];
