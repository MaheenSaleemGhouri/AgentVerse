"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { updateOrganizationSettingsAction } from "@/lib/api/actions";
import type { UpdateOrganizationSettingsRequest } from "@/lib/api/organization-settings";
import { queryKeys } from "@/lib/queries/keys";

export function useUpdateOrganizationSettings(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateOrganizationSettingsRequest) =>
      updateOrganizationSettingsAction(organizationId, body),
    onSuccess: (settings) => {
      queryClient.setQueryData(queryKeys.organizationSettings(organizationId), settings);
      toast.success("Organization profile saved.");
    },
    onError: () => toast.error("Could not save the organization profile."),
  });
}
