"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createCustomRoleAction,
  deleteCustomRoleAction,
  listBuiltinRolesAction,
  listCustomRolesAction,
  updateCustomRoleAction,
} from "@/lib/api/actions";
import type {
  CreateCustomRoleRequest,
  CustomRole,
  RoleDescriptor,
  UpdateCustomRoleRequest,
} from "@/lib/api/roles";
import { queryKeys } from "@/lib/queries/keys";

/**
 * The built-in matrix never changes between deploys, so it is cached
 * aggressively — refetching it on every focus would be pure noise.
 */
export function useBuiltinRoles(workspaceId: string, initialData?: RoleDescriptor[]) {
  return useQuery({
    queryKey: queryKeys.builtinRoles(workspaceId),
    queryFn: () => listBuiltinRolesAction(workspaceId),
    staleTime: 60 * 60 * 1000,
    ...(initialData ? { initialData } : {}),
  });
}

export function useCustomRoles(workspaceId: string, initialData?: CustomRole[]) {
  return useQuery({
    queryKey: queryKeys.customRoles(workspaceId),
    queryFn: () => listCustomRolesAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useCreateCustomRole(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateCustomRoleRequest) => createCustomRoleAction(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.customRoles(workspaceId) });
      toast.success("Role created.");
    },
    onError: () => toast.error("Could not create the role. Only admins can define roles."),
  });
}

export function useUpdateCustomRole(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ roleId, body }: { roleId: string; body: UpdateCustomRoleRequest }) =>
      updateCustomRoleAction(workspaceId, roleId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.customRoles(workspaceId) });
      toast.success("Role updated.");
    },
    onError: () => toast.error("Could not update the role."),
  });
}

export function useDeleteCustomRole(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (roleId: string) => deleteCustomRoleAction(workspaceId, roleId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.customRoles(workspaceId) });
      // Members holding the role fall back to their base tier rather than
      // losing access, so this is worth saying rather than a bare "Deleted".
      toast.success("Role deleted. Members fall back to their base role.");
    },
    onError: () => toast.error("Could not delete the role."),
  });
}
