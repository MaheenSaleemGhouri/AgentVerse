"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  grantResourcePermissionAction,
  listResourcePermissionsAction,
  revokeResourcePermissionAction,
} from "@/lib/api/actions";
import type {
  GrantResourcePermissionRequest,
  ResourcePermission,
} from "@/lib/api/resource-permissions";
import { queryKeys } from "@/lib/queries/keys";

export function useResourcePermissions(workspaceId: string, initialData?: ResourcePermission[]) {
  return useQuery({
    queryKey: queryKeys.resourcePermissions(workspaceId),
    queryFn: () => listResourcePermissionsAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useGrantResourcePermission(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GrantResourcePermissionRequest) =>
      grantResourcePermissionAction(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.resourcePermissions(workspaceId),
      });
      toast.success("Permission granted.");
    },
    onError: () => toast.error("Could not grant the permission — you may not have permission."),
  });
}

export function useRevokeResourcePermission(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (permissionId: string) =>
      revokeResourcePermissionAction(workspaceId, permissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.resourcePermissions(workspaceId),
      });
      toast.success("Permission revoked.");
    },
    onError: () => toast.error("Could not revoke the permission."),
  });
}
