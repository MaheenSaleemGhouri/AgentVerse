"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  addIpAllowlistEntryAction,
  listIpAllowlistAction,
  removeIpAllowlistEntryAction,
} from "@/lib/api/actions";
import type { AddIpAllowlistEntryRequest, IpAllowlistEntry } from "@/lib/api/ip-allowlist";
import { queryKeys } from "@/lib/queries/keys";

export function useIpAllowlist(workspaceId: string, initialData?: IpAllowlistEntry[]) {
  return useQuery({
    queryKey: queryKeys.ipAllowlist(workspaceId),
    queryFn: () => listIpAllowlistAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useAddIpAllowlistEntry(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AddIpAllowlistEntryRequest) =>
      addIpAllowlistEntryAction(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.ipAllowlist(workspaceId) });
      toast.success("IP range added — this workspace is now restricted.");
    },
    onError: () => toast.error("Could not add the range — check the CIDR format."),
  });
}

export function useRemoveIpAllowlistEntry(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) => removeIpAllowlistEntryAction(workspaceId, entryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.ipAllowlist(workspaceId) });
      toast.success("IP range removed.");
    },
    onError: () => toast.error("Could not remove the range."),
  });
}
