"use server";

/**
 * Server Actions wrapping lib/api/workspaces.ts's mutations — the
 * server-only `apiFetch` (needs `next/headers` for the session) can't
 * be called directly from a Client Component (Next.js build correctly
 * rejects that); these thin `"use server"` wrappers are the supported
 * bridge. Read-only calls stay as plain functions invoked from Server
 * Components (create-workspace-form.tsx's parent, the [workspaceId]
 * page) — only client-triggered mutations need this file.
 */

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
