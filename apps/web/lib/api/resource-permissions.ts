import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type ResourcePermission = components["schemas"]["ResourcePermissionResponse"];
export type GrantResourcePermissionRequest =
  components["schemas"]["GrantResourcePermissionRequest"];

export async function listResourcePermissions(
  workspaceId: string
): Promise<ResourcePermission[]> {
  return apiFetch<ResourcePermission[]>(`/api/v1/workspaces/${workspaceId}/resource-permissions`);
}

export async function grantResourcePermission(
  workspaceId: string,
  body: GrantResourcePermissionRequest
): Promise<ResourcePermission> {
  return apiFetch<ResourcePermission>(`/api/v1/workspaces/${workspaceId}/resource-permissions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function revokeResourcePermission(
  workspaceId: string,
  permissionId: string
): Promise<void> {
  await apiFetch<void>(
    `/api/v1/workspaces/${workspaceId}/resource-permissions/${permissionId}`,
    { method: "DELETE", skipJson: true }
  );
}
