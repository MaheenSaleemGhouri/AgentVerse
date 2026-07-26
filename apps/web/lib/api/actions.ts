"use server";

/**
 * Server Actions wrapping lib/api/workspaces.ts's and lib/api/agents.ts's
 * mutations — the
 * server-only `apiFetch` (needs `next/headers` for the session) can't
 * be called directly from a Client Component (Next.js build correctly
 * rejects that); these thin `"use server"` wrappers are the supported
 * bridge. Read-only calls stay as plain functions invoked from Server
 * Components (create-workspace-form.tsx's parent, the [workspaceId]
 * page) — only client-triggered mutations need this file.
 */

import {
  type Agent,
  type AgentVersion,
  createAgent as createAgentApi,
  createAgentVersion as createAgentVersionApi,
  deleteAgent as deleteAgentApi,
  publishAgent as publishAgentApi,
  type Run,
  runAgent as runAgentApi,
  type UpdateAgentVersionRequest,
} from "@/lib/api/agents";
import {
  changeMemberRole as changeMemberRoleApi,
  createWorkspace as createWorkspaceApi,
  inviteMember as inviteMemberApi,
  removeMember as removeMemberApi,
  type Role,
  type Workspace,
} from "@/lib/api/workspaces";

export async function createWorkspaceAction(name: string): Promise<Workspace> {
  return createWorkspaceApi(name);
}

export async function inviteMemberAction(
  workspaceId: string,
  userId: string,
  role: Role
): Promise<void> {
  await inviteMemberApi(workspaceId, userId, role);
}

export async function changeMemberRoleAction(
  workspaceId: string,
  targetUserId: string,
  role: Role
): Promise<void> {
  await changeMemberRoleApi(workspaceId, targetUserId, role);
}

export async function removeMemberAction(workspaceId: string, targetUserId: string): Promise<void> {
  await removeMemberApi(workspaceId, targetUserId);
}

export async function createAgentAction(
  workspaceId: string,
  name: string,
  description: string | null
): Promise<{ agent: Agent; version: AgentVersion }> {
  return createAgentApi(workspaceId, {
    name,
    description,
    model: "gpt-4o-mini",
    system_instructions: "You are a helpful assistant.",
  });
}

export async function saveAgentVersionAction(
  workspaceId: string,
  agentId: string,
  body: UpdateAgentVersionRequest
): Promise<AgentVersion> {
  return createAgentVersionApi(workspaceId, agentId, body);
}

export async function publishAgentAction(workspaceId: string, agentId: string): Promise<Agent> {
  return publishAgentApi(workspaceId, agentId);
}

export async function deleteAgentAction(workspaceId: string, agentId: string): Promise<void> {
  await deleteAgentApi(workspaceId, agentId);
}

export async function runAgentAction(
  workspaceId: string,
  agentId: string,
  prompt: string,
  idempotencyKey: string
): Promise<Run> {
  return runAgentApi(workspaceId, agentId, prompt, idempotencyKey);
}
