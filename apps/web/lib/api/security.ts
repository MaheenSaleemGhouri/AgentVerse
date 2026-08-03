import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/** Generated from the API schema — never mirrored by hand. */
export type SecurityEvent = components["schemas"]["SecurityEventResponse"];
export type SecuritySeverity = components["schemas"]["SecuritySeverity"];
export type TrustedDevice = components["schemas"]["TrustedDeviceResponse"];
export type SecurityScore = components["schemas"]["SecurityScoreResponse"];
export type ScoreFactor = components["schemas"]["ScoreFactorResponse"];
export type PasswordPolicy = components["schemas"]["PasswordPolicyResponse"];
export type UpdatePasswordPolicyRequest =
  components["schemas"]["UpdatePasswordPolicyRequest"];

export async function listMySecurityEvents(limit = 50): Promise<SecurityEvent[]> {
  return apiFetch<SecurityEvent[]>(`/api/v1/me/security/events?limit=${limit}`);
}

export async function listMyDevices(): Promise<TrustedDevice[]> {
  return apiFetch<TrustedDevice[]>("/api/v1/me/security/devices");
}

export async function trustDevice(body: {
  device_fingerprint: string;
  device_name: string | null;
}): Promise<TrustedDevice> {
  return apiFetch<TrustedDevice>("/api/v1/me/security/devices", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function revokeDevice(deviceId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/me/security/devices/${deviceId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function listWorkspaceSecurityEvents(
  workspaceId: string,
  limit = 50
): Promise<SecurityEvent[]> {
  return apiFetch<SecurityEvent[]>(
    `/api/v1/workspaces/${workspaceId}/security/events?limit=${limit}`
  );
}

export async function getSecurityScore(workspaceId: string): Promise<SecurityScore> {
  return apiFetch<SecurityScore>(`/api/v1/workspaces/${workspaceId}/security/score`);
}

export async function getPasswordPolicy(organizationId: string): Promise<PasswordPolicy> {
  return apiFetch<PasswordPolicy>(`/api/v1/organizations/${organizationId}/password-policy`);
}

export async function setPasswordPolicy(
  organizationId: string,
  body: UpdatePasswordPolicyRequest
): Promise<PasswordPolicy> {
  return apiFetch<PasswordPolicy>(`/api/v1/organizations/${organizationId}/password-policy`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
