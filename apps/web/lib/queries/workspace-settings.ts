"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { updateWorkspaceSettingsAction } from "@/lib/api/actions";
import type { UpdateWorkspaceSettingsRequest } from "@/lib/api/workspace-settings";
import { queryKeys } from "@/lib/queries/keys";

export function useUpdateWorkspaceSettings(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateWorkspaceSettingsRequest) =>
      updateWorkspaceSettingsAction(workspaceId, body),
    onSuccess: (settings) => {
      queryClient.setQueryData(queryKeys.workspaceSettings(workspaceId), settings);
      toast.success("Workspace settings saved.");
    },
    onError: () => toast.error("Could not save workspace settings."),
  });
}
