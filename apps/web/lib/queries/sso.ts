"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  deleteSsoConfigurationAction,
  listSsoConfigurationsAction,
  saveSsoConfigurationAction,
} from "@/lib/api/actions";
import type { SaveSsoConfigurationRequest, SsoConfiguration } from "@/lib/api/sso";
import { queryKeys } from "@/lib/queries/keys";

export function useSsoConfigurations(
  organizationId: string,
  initialData?: SsoConfiguration[]
) {
  return useQuery({
    queryKey: queryKeys.ssoConfigurations(organizationId),
    queryFn: () => listSsoConfigurationsAction(organizationId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useSaveSsoConfiguration(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SaveSsoConfigurationRequest) =>
      saveSsoConfigurationAction(organizationId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.ssoConfigurations(organizationId),
      });
      toast.success("SSO configuration saved.");
    },
    onError: () => toast.error("Could not save the configuration."),
  });
}

export function useDeleteSsoConfiguration(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (configId: string) => deleteSsoConfigurationAction(organizationId, configId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.ssoConfigurations(organizationId),
      });
      toast.success("SSO configuration removed.");
    },
    onError: () => toast.error("Could not remove the configuration."),
  });
}
