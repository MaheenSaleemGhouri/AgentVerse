"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  changeMemberRoleAction,
  inviteMemberAction,
  issueApiKeyAction,
  listApiKeysAction,
  listMembersAction,
  removeMemberAction,
  revokeApiKeyAction,
} from "@/lib/api/actions";
import type { ApiKey, Member, Role } from "@/lib/api/workspaces";
import { queryKeys } from "@/lib/queries/keys";

export function useMembers(workspaceId: string, initialData?: Member[]) {
  return useQuery({
    queryKey: queryKeys.members(workspaceId),
    queryFn: () => listMembersAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useInviteMember(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
      inviteMemberAction(workspaceId, userId, role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
      toast.success("Member added.");
    },
    onError: () =>
      toast.error("Could not add the member — check the user ID and your permissions."),
  });
}

export function useChangeMemberRole(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetUserId, role }: { targetUserId: string; role: Role }) =>
      changeMemberRoleAction(workspaceId, targetUserId, role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
      toast.success("Role updated.");
    },
    onError: () => toast.error("Could not change the role — you may not have permission."),
  });
}

export function useRemoveMember(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetUserId: string) => removeMemberAction(workspaceId, targetUserId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
      toast.success("Member removed.");
    },
    onError: () => toast.error("Could not remove the member — you may not have permission."),
  });
}

export function useApiKeys(workspaceId: string, initialData?: ApiKey[]) {
  return useQuery({
    queryKey: queryKeys.apiKeys(workspaceId),
    queryFn: () => listApiKeysAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

/**
 * The issued key's plaintext value is returned exactly once, by this
 * mutation, and is never cached — it is not in any query the list hook
 * reads. The caller must show it immediately or it is unrecoverable.
 */
export function useIssueApiKey(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => issueApiKeyAction(workspaceId, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys(workspaceId) });
    },
    onError: () => toast.error("Could not issue the key — try again."),
  });
}

export function useRevokeApiKey(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (apiKeyId: string) => revokeApiKeyAction(workspaceId, apiKeyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys(workspaceId) });
      toast.success("Key revoked — any client using it will now be rejected.");
    },
    onError: () => toast.error("Could not revoke the key — try again."),
  });
}
