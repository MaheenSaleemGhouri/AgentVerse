import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type SsoConfiguration = components["schemas"]["SsoConfigurationResponse"];
export type SaveSsoConfigurationRequest =
  components["schemas"]["SaveSsoConfigurationRequest"];
export type SsoProtocol = components["schemas"]["SsoProtocol"];
export type SsoPreset = components["schemas"]["SsoPreset"];

export async function listSsoConfigurations(
  organizationId: string
): Promise<SsoConfiguration[]> {
  return apiFetch<SsoConfiguration[]>(`/api/v1/organizations/${organizationId}/sso`);
}

export async function saveSsoConfiguration(
  organizationId: string,
  body: SaveSsoConfigurationRequest
): Promise<SsoConfiguration> {
  return apiFetch<SsoConfiguration>(`/api/v1/organizations/${organizationId}/sso`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteSsoConfiguration(
  organizationId: string,
  configId: string
): Promise<void> {
  await apiFetch<void>(`/api/v1/organizations/${organizationId}/sso/${configId}`, {
    method: "DELETE",
    skipJson: true,
  });
}
