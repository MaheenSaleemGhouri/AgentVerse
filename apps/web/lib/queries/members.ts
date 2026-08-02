"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  changeScopedMemberRoleAction,
  inviteScopedMemberByEmailAction,
  listScopedMembersAction,
  removeScopedMemberAction,
} from "@/lib/api/actions";
import type { MemberScope, ScopedMember } from "@/lib/api/members";
import type { InviteByEmailResponse, Role } from "@/lib/api/workspaces";
import { queryKeys } from "@/lib/queries/keys";

/** Scope-generic member hooks — `MembersTable`/`InviteMemberDialog`'s
 * only data dependency, usable unmodified for a workspace or an
 * organization by passing a different `scope` (CLAUDE.md §16 DRY). */

export function useScopedMembers(scope: MemberScope, initialData?: ScopedMember[]) {
  return useQuery({
    queryKey: queryKeys.scopedMembers(scope),
    queryFn: () => listScopedMembersAction(scope),
    ...(initialData ? { initialData } : {}),
  });
}

export function useInviteScopedMemberByEmail(scope: MemberScope) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, role }: { email: string; role: Role }) =>
      inviteScopedMemberByEmailAction(scope, email, role),
    onSuccess: (result: InviteByEmailResponse) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scopedMembers(scope) });
      toast.success(
        result.status === "added"
          ? "Member added."
          : "Invitation sent — they'll join once they accept it."
      );
    },
    onError: () => toast.error("Could not send the invitation — you may not have permission."),
  });
}

export function useChangeScopedMemberRole(scope: MemberScope) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetUserId, role }: { targetUserId: string; role: Role }) =>
      changeScopedMemberRoleAction(scope, targetUserId, role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scopedMembers(scope) });
      toast.success("Role updated.");
    },
    onError: () => toast.error("Could not change the role — you may not have permission."),
  });
}

export function useRemoveScopedMember(scope: MemberScope) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetUserId: string) => removeScopedMemberAction(scope, targetUserId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.scopedMembers(scope) });
      toast.success("Member removed.");
    },
    onError: () => toast.error("Could not remove the member — you may not have permission."),
  });
}
