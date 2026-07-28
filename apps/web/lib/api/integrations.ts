import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * MCP integrations — the marketplace, installations, credentials,
 * permissions, and runtime reads.
 *
 * Every type is generated from the API's OpenAPI schema, so a backend
 * field rename fails the build here rather than becoming `undefined` at
 * runtime.
 *
 * Note what is **absent**: there is no `getCredential`. The API has no
 * endpoint that returns a credential value, so there is nothing to wrap.
 * `CredentialResponse` carries a four-character hint and metadata.
 */

export type McpServer = components["schemas"]["McpServerResponse"];
export type InstalledServer = components["schemas"]["InstalledServerResponse"];
export type ToolSummary = components["schemas"]["ToolSummary"];
export type Credential = components["schemas"]["CredentialResponse"];
export type Permission = components["schemas"]["PermissionResponse"];
export type ToolCall = components["schemas"]["ToolCallResponse"];
export type ToolCallPage = components["schemas"]["ToolCallPage"];
export type IntegrationMetrics = components["schemas"]["IntegrationMetricsResponse"];
export type InstallFromCatalogRequest = components["schemas"]["InstallFromCatalogRequest"];
export type RegisterCustomServerRequest =
  components["schemas"]["RegisterCustomServerRequest"];
export type UpdateInstalledServerRequest =
  components["schemas"]["UpdateInstalledServerRequest"];
export type PutCredentialRequest = components["schemas"]["PutCredentialRequest"];
export type GrantPermissionRequest = components["schemas"]["GrantPermissionRequest"];

export type Transport = McpServer["transport"];
export type Availability = McpServer["availability"];
export type AuthScheme = McpServer["auth_scheme"];
export type InstallStatus = InstalledServer["status"];
export type Health = InstalledServer["health"];
export type PermissionLevel = Permission["level"];
export type ToolCallStatus = ToolCall["status"];

function base(workspaceId: string): string {
  return `/api/v1/workspaces/${workspaceId}/integrations`;
}

export async function listCatalog(
  workspaceId: string,
  options: { category?: string; q?: string } = {}
): Promise<McpServer[]> {
  const params = new URLSearchParams();
  if (options.category) params.set("category", options.category);
  if (options.q) params.set("q", options.q);
  const query = params.toString();
  return apiFetch<McpServer[]>(`${base(workspaceId)}/catalog${query ? `?${query}` : ""}`);
}

export async function listInstalled(workspaceId: string): Promise<InstalledServer[]> {
  return apiFetch<InstalledServer[]>(base(workspaceId));
}

export async function getInstalled(
  workspaceId: string,
  installedServerId: string
): Promise<InstalledServer> {
  return apiFetch<InstalledServer>(`${base(workspaceId)}/${installedServerId}`);
}

export async function installFromCatalog(
  workspaceId: string,
  body: InstallFromCatalogRequest
): Promise<InstalledServer> {
  return apiFetch<InstalledServer>(base(workspaceId), {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function registerCustomServer(
  workspaceId: string,
  body: RegisterCustomServerRequest
): Promise<InstalledServer> {
  return apiFetch<InstalledServer>(`${base(workspaceId)}/custom`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateInstalled(
  workspaceId: string,
  installedServerId: string,
  body: UpdateInstalledServerRequest
): Promise<InstalledServer> {
  return apiFetch<InstalledServer>(`${base(workspaceId)}/${installedServerId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function uninstall(
  workspaceId: string,
  installedServerId: string
): Promise<void> {
  await apiFetch<void>(`${base(workspaceId)}/${installedServerId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function putCredential(
  workspaceId: string,
  installedServerId: string,
  body: PutCredentialRequest
): Promise<Credential> {
  return apiFetch<Credential>(`${base(workspaceId)}/${installedServerId}/credentials`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function listCredentials(
  workspaceId: string,
  installedServerId: string
): Promise<Credential[]> {
  return apiFetch<Credential[]>(`${base(workspaceId)}/${installedServerId}/credentials`);
}

export async function deleteCredential(
  workspaceId: string,
  installedServerId: string,
  key: string
): Promise<void> {
  await apiFetch<void>(
    `${base(workspaceId)}/${installedServerId}/credentials/${encodeURIComponent(key)}`,
    { method: "DELETE", skipJson: true }
  );
}

export async function grantPermission(
  workspaceId: string,
  installedServerId: string,
  body: GrantPermissionRequest
): Promise<Permission> {
  return apiFetch<Permission>(`${base(workspaceId)}/${installedServerId}/permissions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listPermissions(
  workspaceId: string,
  installedServerId: string,
  agentId?: string
): Promise<Permission[]> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  return apiFetch<Permission[]>(
    `${base(workspaceId)}/${installedServerId}/permissions${query}`
  );
}

export async function revokePermission(
  workspaceId: string,
  installedServerId: string,
  permissionId: string
): Promise<void> {
  await apiFetch<void>(
    `${base(workspaceId)}/${installedServerId}/permissions/${permissionId}`,
    { method: "DELETE", skipJson: true }
  );
}

export async function listToolCalls(
  workspaceId: string,
  // `| undefined` spelled out under `exactOptionalPropertyTypes`:
  // "absent" and "present but undefined" are different types, and every
  // caller here builds these filters by spreading optional values.
  options: {
    installedServerId?: string | undefined;
    runId?: string | undefined;
    status?: string | undefined;
    limit?: number | undefined;
    cursor?: string | undefined;
  } = {}
): Promise<ToolCallPage> {
  const params = new URLSearchParams();
  if (options.installedServerId) params.set("installed_server_id", options.installedServerId);
  if (options.runId) params.set("run_id", options.runId);
  if (options.status) params.set("call_status", options.status);
  if (options.limit) params.set("limit", String(options.limit));
  if (options.cursor) params.set("cursor", options.cursor);
  const query = params.toString();
  return apiFetch<ToolCallPage>(`${base(workspaceId)}/runtime/calls${query ? `?${query}` : ""}`);
}

export async function getIntegrationMetrics(
  workspaceId: string,
  installedServerId?: string
): Promise<IntegrationMetrics> {
  const query = installedServerId
    ? `?installed_server_id=${encodeURIComponent(installedServerId)}`
    : "";
  return apiFetch<IntegrationMetrics>(`${base(workspaceId)}/runtime/metrics${query}`);
}
