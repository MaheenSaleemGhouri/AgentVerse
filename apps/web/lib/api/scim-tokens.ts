import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type ScimToken = components["schemas"]["ScimTokenResponse"];
export type IssuedScimToken = components["schemas"]["IssuedScimTokenResponse"];

export async function listScimTokens(organizationId: string): Promise<ScimToken[]> {
  return apiFetch<ScimToken[]>(`/api/v1/organizations/${organizationId}/scim-tokens`);
}

export async function issueScimToken(
  organizationId: string,
  name: string
): Promise<IssuedScimToken> {
  return apiFetch<IssuedScimToken>(
    `/api/v1/organizations/${organizationId}/scim-tokens`,
    { method: "POST", body: JSON.stringify({ name }) }
  );
}

export async function revokeScimToken(
  organizationId: string,
  tokenId: string
): Promise<void> {
  await apiFetch<void>(
    `/api/v1/organizations/${organizationId}/scim-tokens/${tokenId}`,
    { method: "DELETE", skipJson: true }
  );
}
