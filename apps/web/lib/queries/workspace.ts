"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  issueApiKeyAction,
  listApiKeysAction,
  revokeApiKeyAction,
  rotateApiKeyAction,
} from "@/lib/api/actions";
import type { ApiKey, IssueApiKeyRequest } from "@/lib/api/workspaces";
import { queryKeys } from "@/lib/queries/keys";

// Member hooks (used by `MembersTable`/`InviteMemberDialog`) live in
// `lib/queries/members.ts` — scope-generic across workspaces and
// organizations rather than forked per scope (CLAUDE.md §16).

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
    mutationFn: (body: IssueApiKeyRequest) => issueApiKeyAction(workspaceId, body),
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

/**
 * The rotated key's plaintext is returned exactly once, the same
 * contract as issuing — never cached, the caller must show it
 * immediately (`useIssueApiKey`'s own doc comment above states why).
 */
export function useRotateApiKey(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (apiKeyId: string) => rotateApiKeyAction(workspaceId, apiKeyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys(workspaceId) });
    },
    onError: () => toast.error("Could not rotate the key — try again."),
  });
}
