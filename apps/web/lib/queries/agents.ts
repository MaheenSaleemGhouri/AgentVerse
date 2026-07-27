"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createAgentAction,
  deleteAgentAction,
  getAgentAction,
  getLatestVersionAction,
  listAgentsAction,
  publishAgentAction,
  saveAgentVersionAction,
} from "@/lib/api/actions";
import type { Agent, AgentVersion, UpdateAgentVersionRequest } from "@/lib/api/agents";
import { queryKeys } from "@/lib/queries/keys";

export function useAgents(workspaceId: string, initialData?: Agent[]) {
  return useQuery({
    queryKey: queryKeys.agents.all(workspaceId),
    queryFn: () => listAgentsAction(workspaceId),
    // Server-rendered first paint seeds the cache, so the list never
    // flashes a skeleton for data the page already had.
    ...(initialData ? { initialData } : {}),
  });
}

export function useAgent(workspaceId: string, agentId: string, initialData?: Agent) {
  return useQuery({
    queryKey: queryKeys.agents.detail(workspaceId, agentId),
    queryFn: () => getAgentAction(workspaceId, agentId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useLatestVersion(
  workspaceId: string,
  agentId: string,
  initialData?: AgentVersion | null
) {
  return useQuery({
    queryKey: queryKeys.agents.latestVersion(workspaceId, agentId),
    queryFn: () => getLatestVersionAction(workspaceId, agentId),
    ...(initialData !== undefined ? { initialData } : {}),
  });
}

export function useCreateAgent(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description: string | null }) =>
      createAgentAction(workspaceId, name, description),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents.all(workspaceId) });
    },
    onError: () => toast.error("Could not create the agent — try again."),
  });
}

export function useSaveAgentVersion(workspaceId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateAgentVersionRequest) =>
      saveAgentVersionAction(workspaceId, agentId, body),
    onSuccess: (version) => {
      // Both the version and the agent row change (updated_at, and the
      // agent's status can move back to draft), so both are invalidated.
      queryClient.setQueryData(queryKeys.agents.latestVersion(workspaceId, agentId), version);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.agents.detail(workspaceId, agentId),
      });
      toast.success(`Saved as version ${version.version_number}`);
    },
    onError: () => toast.error("Could not save changes — try again."),
  });
}

export function usePublishAgent(workspaceId: string, agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => publishAgentAction(workspaceId, agentId),
    onSuccess: (agent) => {
      queryClient.setQueryData(queryKeys.agents.detail(workspaceId, agentId), agent);
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents.all(workspaceId) });
      toast.success("Agent published — it can now be run.");
    },
    onError: () => toast.error("Could not publish the agent — try again."),
  });
}

export function useDeleteAgent(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => deleteAgentAction(workspaceId, agentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.agents.all(workspaceId) });
      toast.success("Agent deleted.");
    },
    onError: () => toast.error("Could not delete the agent — try again."),
  });
}
