"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  attachWorkspaceAction,
  createOrganizationAction,
  deleteOrganizationAction,
  detachWorkspaceAction,
  listMyOrganizationsAction,
  listOrgWorkspacesAction,
  renameOrganizationAction,
} from "@/lib/api/actions";
import type { Organization, OrganizationWorkspace } from "@/lib/api/organizations";
import { queryKeys } from "@/lib/queries/keys";

export function useMyOrganizations(initialData?: Organization[]) {
  return useQuery({
    queryKey: queryKeys.organizations(),
    queryFn: () => listMyOrganizationsAction(),
    ...(initialData ? { initialData } : {}),
  });
}

export function useCreateOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createOrganizationAction(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.organizations() });
    },
    onError: () => toast.error("Could not create the organization — try a different name."),
  });
}

export function useRenameOrganization(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => renameOrganizationAction(organizationId, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.organizations() });
      toast.success("Organization renamed.");
    },
    onError: () => toast.error("Could not rename the organization."),
  });
}

export function useDeleteOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (organizationId: string) => deleteOrganizationAction(organizationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.organizations() });
      toast.success("Organization deleted — its workspaces were detached, not deleted.");
    },
    onError: () => toast.error("Could not delete the organization."),
  });
}

export function useOrgWorkspaces(organizationId: string, initialData?: OrganizationWorkspace[]) {
  return useQuery({
    queryKey: queryKeys.organizationWorkspaces(organizationId),
    queryFn: () => listOrgWorkspacesAction(organizationId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useAttachWorkspace(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workspaceId: string) => attachWorkspaceAction(organizationId, workspaceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.organizationWorkspaces(organizationId),
      });
      toast.success("Workspace attached.");
    },
    onError: () =>
      toast.error("Could not attach the workspace — you must own both the org and the workspace."),
  });
}

export function useDetachWorkspace(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workspaceId: string) => detachWorkspaceAction(organizationId, workspaceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.organizationWorkspaces(organizationId),
      });
      toast.success("Workspace detached — it was not deleted.");
    },
    onError: () => toast.error("Could not detach the workspace."),
  });
}
