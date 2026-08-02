import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * Every type below is generated from the API's OpenAPI schema — never
 * hand-written, so a backend field rename fails the build here rather
 * than becoming `undefined` at runtime.
 */
export type WorkspaceSettings = components["schemas"]["WorkspaceSettingsResponse"];
export type UpdateWorkspaceSettingsRequest = components["schemas"]["UpdateWorkspaceSettingsRequest"];

export async function getWorkspaceSettings(workspaceId: string): Promise<WorkspaceSettings> {
  return apiFetch<WorkspaceSettings>(`/api/v1/workspaces/${workspaceId}/settings`);
}

export async function updateWorkspaceSettings(
  workspaceId: string,
  body: UpdateWorkspaceSettingsRequest
): Promise<WorkspaceSettings> {
  return apiFetch<WorkspaceSettings>(`/api/v1/workspaces/${workspaceId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
