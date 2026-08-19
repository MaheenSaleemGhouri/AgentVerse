"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createWorkflowAction,
  createWorkflowVersionAction,
  getLatestWorkflowVersionAction,
  getWorkflowAction,
  getWorkflowRunAction,
  listWorkflowRunNodesAction,
  listWorkflowsAction,
  publishWorkflowAction,
  resolveWorkflowApprovalAction,
  submitWorkflowRunAction,
} from "@/lib/api/actions";
import type {
  CreateWorkflowRequest,
  CreateWorkflowVersionRequest,
  Workflow,
  WorkflowNodeRun,
  WorkflowRun,
  WorkflowVersion,
} from "@/lib/api/workflows";
import { queryKeys } from "@/lib/queries/keys";

export function useWorkflows(workspaceId: string, initialData?: Workflow[]) {
  return useQuery({
    queryKey: queryKeys.workflows.all(workspaceId),
    queryFn: () => listWorkflowsAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useWorkflow(workspaceId: string, workflowId: string, initialData?: Workflow) {
  return useQuery({
    queryKey: queryKeys.workflows.detail(workspaceId, workflowId),
    queryFn: () => getWorkflowAction(workspaceId, workflowId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useLatestWorkflowVersion(
  workspaceId: string,
  workflowId: string,
  initialData?: WorkflowVersion | null
) {
  return useQuery({
    queryKey: queryKeys.workflows.latestVersion(workspaceId, workflowId),
    queryFn: () => getLatestWorkflowVersionAction(workspaceId, workflowId),
    ...(initialData !== undefined ? { initialData } : {}),
  });
}

export function useCreateWorkflow(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateWorkflowRequest) => createWorkflowAction(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflows.all(workspaceId) });
    },
    onError: () => toast.error("Could not create the workflow — try again."),
  });
}

export function useCreateWorkflowVersion(workspaceId: string, workflowId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateWorkflowVersionRequest) =>
      createWorkflowVersionAction(workspaceId, workflowId, body),
    onSuccess: (version) => {
      queryClient.setQueryData(
        queryKeys.workflows.latestVersion(workspaceId, workflowId),
        version
      );
      toast.success(`Saved as version ${version.version_number}`);
    },
    onError: () => toast.error("Could not save changes — try again."),
  });
}

export function usePublishWorkflow(workspaceId: string, workflowId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (versionId: string) => publishWorkflowAction(workspaceId, workflowId, versionId),
    onSuccess: (workflow) => {
      queryClient.setQueryData(queryKeys.workflows.detail(workspaceId, workflowId), workflow);
      void queryClient.invalidateQueries({ queryKey: queryKeys.workflows.all(workspaceId) });
      toast.success("Workflow published — it can now be run.");
    },
    onError: () => toast.error("Could not publish the workflow — try again."),
  });
}

export function useSubmitWorkflowRun(workspaceId: string, workflowId: string) {
  return useMutation({
    mutationFn: (input: Record<string, unknown>) =>
      submitWorkflowRunAction(workspaceId, workflowId, input, crypto.randomUUID()),
    onError: () => toast.error("Could not start the run — try again."),
  });
}

const RUN_POLL_INTERVAL_MS = 2000;
const TERMINAL_RUN_STATUSES = new Set(["success", "error", "cancelled"]);

/**
 * Per-node DAG execution has no SSE stream in this phase's cut
 * (docs/adr/0016: nodes complete on the order of seconds-to-minutes, not
 * token-by-token) — polling via TanStack Query's `refetchInterval` is
 * the whole mechanism, and it stops itself once the run reaches a
 * terminal status rather than polling forever.
 */
export function useWorkflowRun(workspaceId: string, workflowId: string, runId: string | null) {
  return useQuery({
    queryKey: queryKeys.workflows.run(workspaceId, workflowId, runId ?? ""),
    queryFn: () => getWorkflowRunAction(workspaceId, workflowId, runId!),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const data = query.state.data as WorkflowRun | undefined;
      return data && TERMINAL_RUN_STATUSES.has(data.status) ? false : RUN_POLL_INTERVAL_MS;
    },
  });
}

export function useWorkflowRunNodes(
  workspaceId: string,
  workflowId: string,
  runId: string | null,
  runStatus: string | undefined
) {
  return useQuery({
    queryKey: queryKeys.workflows.runNodes(workspaceId, workflowId, runId ?? ""),
    queryFn: () => listWorkflowRunNodesAction(workspaceId, workflowId, runId!),
    enabled: runId !== null,
    refetchInterval: runStatus && TERMINAL_RUN_STATUSES.has(runStatus) ? false : RUN_POLL_INTERVAL_MS,
  });
}

export function useResolveWorkflowApproval(workspaceId: string, workflowId: string, runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      nodeId,
      decision,
      comment,
    }: {
      nodeId: string;
      decision: "approved" | "rejected";
      comment: string | null;
    }) => resolveWorkflowApprovalAction(workspaceId, workflowId, runId, nodeId, decision, comment),
    onSuccess: (nodeRun: WorkflowNodeRun) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.workflows.runNodes(workspaceId, workflowId, runId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.workflows.run(workspaceId, workflowId, runId),
      });
      toast.success(
        nodeRun.approval_decision === "approved" ? "Approved — resuming the run." : "Rejected."
      );
    },
    onError: () => toast.error("Could not record the decision — try again."),
  });
}
