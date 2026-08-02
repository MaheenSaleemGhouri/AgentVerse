import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type Workspace = components["schemas"]["WorkspaceResponse"];
export type Member = components["schemas"]["MemberResponse"];
export type Role = components["schemas"]["Role"];
export type IssuedApiKey = components["schemas"]["IssuedApiKeyResponse"];
export type ApiKey = components["schemas"]["ApiKeyResponse"];
export type ApiKeyScope = ApiKey["scope"];
export type IssueApiKeyRequest = components["schemas"]["IssueApiKeyRequest"];
export type InviteByEmailResponse = components["schemas"]["InviteByEmailResponse"];

export async function listMyWorkspaces(): Promise<Workspace[]> {
  return apiFetch<Workspace[]>("/api/v1/workspaces");
}

export async function createWorkspace(name: string): Promise<Workspace> {
  return apiFetch<Workspace>("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiFetch<Workspace>(`/api/v1/workspaces/${workspaceId}`);
}

export async function listMembers(workspaceId: string): Promise<Member[]> {
  return apiFetch<Member[]>(`/api/v1/workspaces/${workspaceId}/members`);
}

/**
 * An email matching an existing account is added immediately
 * (`status: "added"`); an unknown email gets a 7-day token and an
 * email dispatch (`status: "invited"`) — the API decides which, not
 * the caller.
 */
export async function inviteWorkspaceMemberByEmail(
  workspaceId: string,
  email: string,
  role: Role
): Promise<InviteByEmailResponse> {
  return apiFetch<InviteByEmailResponse>(`/api/v1/workspaces/${workspaceId}/invitations`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function changeMemberRole(
  workspaceId: string,
  targetUserId: string,
  role: Role
): Promise<Member> {
  return apiFetch<Member>(`/api/v1/workspaces/${workspaceId}/members/${targetUserId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export async function removeMember(workspaceId: string, targetUserId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/workspaces/${workspaceId}/members/${targetUserId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function issueApiKey(
  workspaceId: string,
  body: IssueApiKeyRequest
): Promise<IssuedApiKey> {
  return apiFetch<IssuedApiKey>(`/api/v1/workspaces/${workspaceId}/api-keys`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listApiKeys(workspaceId: string): Promise<ApiKey[]> {
  return apiFetch<ApiKey[]>(`/api/v1/workspaces/${workspaceId}/api-keys`);
}

export async function revokeApiKey(workspaceId: string, apiKeyId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/workspaces/${workspaceId}/api-keys/${apiKeyId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function rotateApiKey(
  workspaceId: string,
  apiKeyId: string
): Promise<IssuedApiKey> {
  return apiFetch<IssuedApiKey>(`/api/v1/workspaces/${workspaceId}/api-keys/${apiKeyId}/rotate`, {
    method: "POST",
  });
}
