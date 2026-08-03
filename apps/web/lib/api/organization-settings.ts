import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * Generated from the API's OpenAPI schema, never hand-written — a
 * backend field rename fails this build instead of silently becoming
 * `undefined` at runtime.
 */
export type OrganizationSettings = components["schemas"]["OrganizationSettingsResponse"];
export type UpdateOrganizationSettingsRequest =
  components["schemas"]["UpdateOrganizationSettingsRequest"];

export async function getOrganizationSettings(
  organizationId: string
): Promise<OrganizationSettings> {
  return apiFetch<OrganizationSettings>(`/api/v1/organizations/${organizationId}/settings`);
}

export async function updateOrganizationSettings(
  organizationId: string,
  body: UpdateOrganizationSettingsRequest
): Promise<OrganizationSettings> {
  return apiFetch<OrganizationSettings>(`/api/v1/organizations/${organizationId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
