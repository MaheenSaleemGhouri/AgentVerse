import type { components } from "@agentverse/contracts";

import { ApiError, apiFetch } from "@/lib/api/client";

export type Workflow = components["schemas"]["WorkflowResponse"];
export type WorkflowVersion = components["schemas"]["WorkflowVersionResponse"];
export type WorkflowNode = components["schemas"]["WorkflowNodeSchema"];
export type WorkflowEdge = components["schemas"]["WorkflowEdgeSchema"];
export type WorkflowNodeType = components["schemas"]["WorkflowNodeType"];
export type WorkflowVersionDiff = components["schemas"]["WorkflowVersionDiffResponse"];
export type WorkflowRun = components["schemas"]["WorkflowRunResponse"];
export type WorkflowNodeRun = components["schemas"]["WorkflowNodeRunResponse"];
export type CreateWorkflowRequest = components["schemas"]["CreateWorkflowRequest"];
export type CreateWorkflowVersionRequest = components["schemas"]["CreateWorkflowVersionRequest"];
export type CollabTicketResponse = components["schemas"]["CollabTicketResponse"];

export const WORKFLOW_NODE_TYPES: readonly WorkflowNodeType[] = [
  "agent_step",
  "team_step",
  "conditional_branch",
  "human_approval",
  "parallel_fanout",
];

export async function listWorkflows(workspaceId: string): Promise<Workflow[]> {
  return apiFetch<Workflow[]>(`/api/v1/workspaces/${workspaceId}/workflows`);
}

export async function getWorkflow(workspaceId: string, workflowId: string): Promise<Workflow> {
  return apiFetch<Workflow>(`/api/v1/workspaces/${workspaceId}/workflows/${workflowId}`);
}

export async function createWorkflow(
  workspaceId: string,
  body: CreateWorkflowRequest
): Promise<{ workflow: Workflow; version: WorkflowVersion }> {
  return apiFetch<{ workflow: Workflow; version: WorkflowVersion }>(
    `/api/v1/workspaces/${workspaceId}/workflows`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function getLatestWorkflowVersion(
  workspaceId: string,
  workflowId: string
): Promise<WorkflowVersion | null> {
  try {
    return await apiFetch<WorkflowVersion>(
      `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/versions/latest`
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getWorkflowVersion(
  workspaceId: string,
  workflowId: string,
  versionId: string
): Promise<WorkflowVersion> {
  return apiFetch<WorkflowVersion>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/versions/${versionId}`
  );
}

export async function createWorkflowVersion(
  workspaceId: string,
  workflowId: string,
  body: CreateWorkflowVersionRequest
): Promise<WorkflowVersion> {
  return apiFetch<WorkflowVersion>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/versions`,
    { method: "POST", body: JSON.stringify(body) }
  );
}

export async function diffWorkflowVersions(
  workspaceId: string,
  workflowId: string,
  versionId: string,
  against: string
): Promise<WorkflowVersionDiff> {
  return apiFetch<WorkflowVersionDiff>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/versions/${versionId}/diff?against=${encodeURIComponent(against)}`
  );
}

export async function publishWorkflow(
  workspaceId: string,
  workflowId: string,
  versionId: string
): Promise<Workflow> {
  return apiFetch<Workflow>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/publish`,
    { method: "POST", body: JSON.stringify({ version_id: versionId }) }
  );
}

export async function submitWorkflowRun(
  workspaceId: string,
  workflowId: string,
  input: Record<string, unknown>,
  idempotencyKey: string
): Promise<WorkflowRun> {
  return apiFetch<WorkflowRun>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/runs`,
    {
      method: "POST",
      body: JSON.stringify({ input }),
      headers: { "Idempotency-Key": idempotencyKey },
    }
  );
}

export async function getWorkflowRun(
  workspaceId: string,
  workflowId: string,
  runId: string
): Promise<WorkflowRun> {
  return apiFetch<WorkflowRun>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/runs/${runId}`
  );
}

export async function listWorkflowRunNodes(
  workspaceId: string,
  workflowId: string,
  runId: string
): Promise<WorkflowNodeRun[]> {
  return apiFetch<WorkflowNodeRun[]>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/runs/${runId}/nodes`
  );
}

export async function resolveWorkflowApproval(
  workspaceId: string,
  workflowId: string,
  runId: string,
  nodeId: string,
  decision: "approved" | "rejected",
  comment: string | null
): Promise<WorkflowNodeRun> {
  return apiFetch<WorkflowNodeRun>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/runs/${runId}/nodes/${nodeId}/resolve`,
    { method: "POST", body: JSON.stringify({ decision, comment }) }
  );
}

export async function mintCollabTicket(
  workspaceId: string,
  workflowId: string
): Promise<CollabTicketResponse> {
  return apiFetch<CollabTicketResponse>(
    `/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/collab-ticket`,
    { method: "POST", skipJson: false }
  );
}
