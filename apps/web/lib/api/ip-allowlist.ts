import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type IpAllowlistEntry = components["schemas"]["IpAllowlistEntryResponse"];
export type AddIpAllowlistEntryRequest =
  components["schemas"]["AddIpAllowlistEntryRequest"];

export async function listIpAllowlist(workspaceId: string): Promise<IpAllowlistEntry[]> {
  return apiFetch<IpAllowlistEntry[]>(`/api/v1/workspaces/${workspaceId}/ip-allowlist`);
}

export async function addIpAllowlistEntry(
  workspaceId: string,
  body: AddIpAllowlistEntryRequest
): Promise<IpAllowlistEntry> {
  return apiFetch<IpAllowlistEntry>(`/api/v1/workspaces/${workspaceId}/ip-allowlist`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function removeIpAllowlistEntry(
  workspaceId: string,
  entryId: string
): Promise<void> {
  await apiFetch<void>(`/api/v1/workspaces/${workspaceId}/ip-allowlist/${entryId}`, {
    method: "DELETE",
    skipJson: true,
  });
}
