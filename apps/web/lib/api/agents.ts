import type { components } from "@agentverse/contracts";

import { ApiError, apiFetch } from "@/lib/api/client";

export type Agent = components["schemas"]["AgentResponse"];
export type AgentVersion = components["schemas"]["AgentVersionResponse"];
export type CreateAgentRequest = components["schemas"]["CreateAgentRequest"];
export type UpdateAgentVersionRequest = components["schemas"]["UpdateAgentVersionRequest"];
export type Run = components["schemas"]["RunResponse"];

export async function listAgents(workspaceId: string): Promise<Agent[]> {
  return apiFetch<Agent[]>(`/api/v1/workspaces/${workspaceId}/agents`);
}

export async function getAgent(workspaceId: string, agentId: string): Promise<Agent> {
  return apiFetch<Agent>(`/api/v1/workspaces/${workspaceId}/agents/${agentId}`);
}

export async function getLatestVersion(
  workspaceId: string,
  agentId: string
): Promise<AgentVersion | null> {
  try {
    return await apiFetch<AgentVersion>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/versions/latest`
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function createAgent(
  workspaceId: string,
  body: CreateAgentRequest
): Promise<{ agent: Agent; version: AgentVersion }> {
  return apiFetch<{ agent: Agent; version: AgentVersion }>(
    `/api/v1/workspaces/${workspaceId}/agents`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function createAgentVersion(
  workspaceId: string,
  agentId: string,
  body: UpdateAgentVersionRequest
): Promise<AgentVersion> {
  return apiFetch<AgentVersion>(`/api/v1/workspaces/${workspaceId}/agents/${agentId}/versions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function publishAgent(workspaceId: string, agentId: string): Promise<Agent> {
  return apiFetch<Agent>(`/api/v1/workspaces/${workspaceId}/agents/${agentId}/publish`, {
    method: "POST",
  });
}

export async function deleteAgent(workspaceId: string, agentId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/workspaces/${workspaceId}/agents/${agentId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function runAgent(
  workspaceId: string,
  agentId: string,
  prompt: string,
  idempotencyKey: string
): Promise<Run> {
  return apiFetch<Run>(`/api/v1/workspaces/${workspaceId}/agents/${agentId}/runs`, {
    method: "POST",
    body: JSON.stringify({ input: { prompt } }),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
