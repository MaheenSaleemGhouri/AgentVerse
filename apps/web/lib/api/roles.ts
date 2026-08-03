import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * The built-in permission matrix is fetched, never mirrored client-side.
 * The server owns what a role may do; a second copy here would be a
 * second source of truth that drifts silently from enforcement.
 */
export type RoleDescriptor = components["schemas"]["RoleDescriptor"];
/**
 * Derived from the descriptor rather than re-declared: regenerating the
 * contract after a permission is added or renamed then breaks every
 * consumer that hasn't been updated, instead of silently widening.
 */
export type Permission = RoleDescriptor["permissions"][number];
export type CustomRole = components["schemas"]["CustomRoleResponse"];
export type CreateCustomRoleRequest = components["schemas"]["CreateCustomRoleRequest"];
export type UpdateCustomRoleRequest = components["schemas"]["UpdateCustomRoleRequest"];

export async function listBuiltinRoles(workspaceId: string): Promise<RoleDescriptor[]> {
  return apiFetch<RoleDescriptor[]>(`/api/v1/workspaces/${workspaceId}/roles/builtin`);
}

export async function listCustomRoles(workspaceId: string): Promise<CustomRole[]> {
  return apiFetch<CustomRole[]>(`/api/v1/workspaces/${workspaceId}/roles`);
}

export async function createCustomRole(
  workspaceId: string,
  body: CreateCustomRoleRequest
): Promise<CustomRole> {
  return apiFetch<CustomRole>(`/api/v1/workspaces/${workspaceId}/roles`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateCustomRole(
  workspaceId: string,
  roleId: string,
  body: UpdateCustomRoleRequest
): Promise<CustomRole> {
  return apiFetch<CustomRole>(`/api/v1/workspaces/${workspaceId}/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteCustomRole(workspaceId: string, roleId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/workspaces/${workspaceId}/roles/${roleId}`, {
    method: "DELETE",
    skipJson: true,
  });
}
