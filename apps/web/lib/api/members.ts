/**
 * Scope-generic membership API — lets `MembersTable`/`InviteMemberDialog`
 * be reused for both workspaces and organizations instead of forking them
 * (CLAUDE.md §16 DRY). `ScopedMember` deliberately carries only the
 * fields both `MemberResponse` and `OrganizationMemberResponse` share
 * (not the parent id, which the caller already has as `scope.id`, and
 * not `suspended_at`, which is organization-only — suspend/reinstate go
 * through `lib/api/organizations.ts` directly).
 */
import type { InviteByEmailResponse, Role } from "@/lib/api/workspaces";
import {
  changeOrgMemberRole,
  inviteOrganizationMemberByEmail,
  listOrgMembers,
  removeOrgMember,
} from "@/lib/api/organizations";
import {
  changeMemberRole,
  inviteWorkspaceMemberByEmail,
  listMembers,
  removeMember,
} from "@/lib/api/workspaces";

export type MemberScope =
  | { type: "workspace"; id: string }
  | { type: "organization"; id: string };

export interface ScopedMember {
  user_id: string;
  role: Role;
  created_at: string;
}

export async function listScopedMembers(scope: MemberScope): Promise<ScopedMember[]> {
  if (scope.type === "workspace") return listMembers(scope.id);
  return listOrgMembers(scope.id);
}

export async function inviteScopedMemberByEmail(
  scope: MemberScope,
  email: string,
  role: Role
): Promise<InviteByEmailResponse> {
  if (scope.type === "workspace") {
    return inviteWorkspaceMemberByEmail(scope.id, email, role);
  }
  return inviteOrganizationMemberByEmail(scope.id, email, role);
}

export async function changeScopedMemberRole(
  scope: MemberScope,
  targetUserId: string,
  role: Role
): Promise<void> {
  if (scope.type === "workspace") {
    await changeMemberRole(scope.id, targetUserId, role);
  } else {
    await changeOrgMemberRole(scope.id, targetUserId, role);
  }
}

export async function removeScopedMember(scope: MemberScope, targetUserId: string): Promise<void> {
  if (scope.type === "workspace") {
    await removeMember(scope.id, targetUserId);
  } else {
    await removeOrgMember(scope.id, targetUserId);
  }
}
