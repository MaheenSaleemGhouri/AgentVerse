import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";
import type { InviteByEmailResponse, Role } from "@/lib/api/workspaces";

export type Organization = components["schemas"]["OrganizationResponse"];
export type OrganizationMember = components["schemas"]["OrganizationMemberResponse"];
export type OrganizationWorkspace = components["schemas"]["OrganizationWorkspaceResponse"];

export async function listMyOrganizations(): Promise<Organization[]> {
  return apiFetch<Organization[]>("/api/v1/organizations");
}

export async function createOrganization(name: string): Promise<Organization> {
  return apiFetch<Organization>("/api/v1/organizations", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function getOrganization(organizationId: string): Promise<Organization> {
  return apiFetch<Organization>(`/api/v1/organizations/${organizationId}`);
}

export async function renameOrganization(
  organizationId: string,
  name: string
): Promise<Organization> {
  return apiFetch<Organization>(`/api/v1/organizations/${organizationId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteOrganization(organizationId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/organizations/${organizationId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function listOrgMembers(organizationId: string): Promise<OrganizationMember[]> {
  return apiFetch<OrganizationMember[]>(`/api/v1/organizations/${organizationId}/members`);
}

export async function inviteOrganizationMemberByEmail(
  organizationId: string,
  email: string,
  role: Role
): Promise<InviteByEmailResponse> {
  return apiFetch<InviteByEmailResponse>(`/api/v1/organizations/${organizationId}/invitations`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function changeOrgMemberRole(
  organizationId: string,
  targetUserId: string,
  role: Role
): Promise<OrganizationMember> {
  return apiFetch<OrganizationMember>(
    `/api/v1/organizations/${organizationId}/members/${targetUserId}`,
    { method: "PATCH", body: JSON.stringify({ role }) }
  );
}

export async function removeOrgMember(
  organizationId: string,
  targetUserId: string
): Promise<void> {
  await apiFetch<void>(`/api/v1/organizations/${organizationId}/members/${targetUserId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function suspendOrgMember(
  organizationId: string,
  targetUserId: string
): Promise<OrganizationMember> {
  return apiFetch<OrganizationMember>(
    `/api/v1/organizations/${organizationId}/members/${targetUserId}/suspend`,
    { method: "POST" }
  );
}

export async function reinstateOrgMember(
  organizationId: string,
  targetUserId: string
): Promise<OrganizationMember> {
  return apiFetch<OrganizationMember>(
    `/api/v1/organizations/${organizationId}/members/${targetUserId}/reinstate`,
    { method: "POST" }
  );
}

export async function listOrgWorkspaces(
  organizationId: string
): Promise<OrganizationWorkspace[]> {
  return apiFetch<OrganizationWorkspace[]>(`/api/v1/organizations/${organizationId}/workspaces`);
}

export async function attachWorkspace(
  organizationId: string,
  workspaceId: string
): Promise<void> {
  await apiFetch<void>(`/api/v1/organizations/${organizationId}/workspaces/${workspaceId}`, {
    method: "POST",
    skipJson: true,
  });
}

export async function detachWorkspace(
  organizationId: string,
  workspaceId: string
): Promise<void> {
  await apiFetch<void>(`/api/v1/organizations/${organizationId}/workspaces/${workspaceId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export type OrganizationDashboard = components["schemas"]["OrganizationDashboardResponse"];
export type MemberPresence = components["schemas"]["MemberPresenceResponse"];

export async function getOrganizationDashboard(
  organizationId: string
): Promise<OrganizationDashboard> {
  return apiFetch<OrganizationDashboard>(`/api/v1/organizations/${organizationId}/dashboard`);
}
