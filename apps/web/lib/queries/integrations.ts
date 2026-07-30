"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  deleteCredentialAction,
  getInstalledAction,
  getIntegrationMetricsAction,
  grantPermissionAction,
  installFromCatalogAction,
  listCatalogAction,
  listCredentialsAction,
  listInstalledAction,
  listPermissionsAction,
  listToolCallsAction,
  putCredentialAction,
  registerCustomServerAction,
  revokePermissionAction,
  startOauthAction,
  uninstallAction,
  updateInstalledAction,
} from "@/lib/api/actions";
import type {
  GrantPermissionRequest,
  InstalledServer,
  McpServer,
  PutCredentialRequest,
  RegisterCustomServerRequest,
  UpdateInstalledServerRequest,
} from "@/lib/api/integrations";
import { queryKeys } from "@/lib/queries/keys";

/** A server still waiting on setup, or one that cannot be reached. */
export function needsAttention(server: InstalledServer): boolean {
  return (
    server.status === "pending_auth" ||
    server.status === "error" ||
    server.health === "unreachable"
  );
}

export function useCatalog(
  workspaceId: string,
  filters: { category?: string; q?: string } = {},
  initialData?: McpServer[]
) {
  return useQuery({
    queryKey: queryKeys.integrations.catalog(workspaceId, filters),
    queryFn: () => listCatalogAction(workspaceId, filters),
    // The catalog is platform data that changes on deploys, not on user
    // action — a long stale time avoids refetching it on every tab
    // switch through the marketplace.
    staleTime: 5 * 60 * 1000,
    ...(initialData ? { initialData } : {}),
  });
}

export function useInstalledServers(workspaceId: string, initialData?: InstalledServer[]) {
  return useQuery({
    queryKey: queryKeys.integrations.installed(workspaceId),
    queryFn: () => listInstalledAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useInstalledServer(
  workspaceId: string,
  installedServerId: string,
  initialData?: InstalledServer
) {
  return useQuery({
    queryKey: queryKeys.integrations.detail(workspaceId, installedServerId),
    queryFn: () => getInstalledAction(workspaceId, installedServerId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useCredentials(workspaceId: string, installedServerId: string) {
  return useQuery({
    queryKey: queryKeys.integrations.credentials(workspaceId, installedServerId),
    queryFn: () => listCredentialsAction(workspaceId, installedServerId),
  });
}

export function usePermissions(
  workspaceId: string,
  installedServerId: string,
  agentId?: string
) {
  return useQuery({
    queryKey: queryKeys.integrations.permissions(workspaceId, installedServerId, agentId),
    queryFn: () => listPermissionsAction(workspaceId, installedServerId, agentId),
  });
}

export function useToolCalls(
  workspaceId: string,
  // `| undefined` spelled out because `exactOptionalPropertyTypes` makes
  // "absent" and "present but undefined" different types, and a caller
  // spreading an optional id passes the latter.
  filters: {
    installedServerId?: string | undefined;
    runId?: string | undefined;
    status?: string | undefined;
  } = {}
) {
  return useQuery({
    queryKey: queryKeys.integrations.calls(workspaceId, filters),
    queryFn: () => listToolCallsAction(workspaceId, { ...filters, limit: 50 }),
    // Tool calls land while a run is in flight, so the runtime view
    // refreshes — but on an interval rather than a stream: unlike a run,
    // there is no single session to subscribe to.
    refetchInterval: 5000,
  });
}

export function useIntegrationMetrics(workspaceId: string, installedServerId?: string) {
  return useQuery({
    queryKey: queryKeys.integrations.metrics(workspaceId, installedServerId),
    queryFn: () => getIntegrationMetricsAction(workspaceId, installedServerId),
    refetchInterval: 30_000,
  });
}

function useInvalidateIntegrations(workspaceId: string) {
  const queryClient = useQueryClient();
  return () =>
    void queryClient.invalidateQueries({
      queryKey: queryKeys.integrations.installed(workspaceId),
    });
}

export function useInstallFromCatalog(workspaceId: string) {
  const invalidate = useInvalidateIntegrations(workspaceId);
  return useMutation({
    mutationFn: (mcpServerId: string) =>
      installFromCatalogAction(workspaceId, { mcp_server_id: mcpServerId }),
    onSuccess: (server) => {
      invalidate();
      toast.success(
        server.status === "pending_auth"
          ? `${server.display_name} installed — add its credentials to finish.`
          : `${server.display_name} installed.`
      );
    },
    onError: (error: Error) =>
      // A 409 here carries the actionable reason: the service has no
      // installable MCP server. Surfacing it verbatim tells the user
      // what to do instead of "something went wrong".
      toast.error(
        error.message.includes("custom server")
          ? "That service has no installable MCP server yet — register your own endpoint."
          : "Could not install — try again."
      ),
  });
}

export function useRegisterCustomServer(workspaceId: string) {
  const invalidate = useInvalidateIntegrations(workspaceId);
  return useMutation({
    mutationFn: (body: RegisterCustomServerRequest) =>
      registerCustomServerAction(workspaceId, body),
    onSuccess: () => {
      invalidate();
      toast.success("Custom server registered.");
    },
    onError: () => toast.error("Could not register the server — check the endpoint URL."),
  });
}

export function useUpdateInstalled(workspaceId: string, installedServerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateInstalledServerRequest) =>
      updateInstalledAction(workspaceId, installedServerId, body),
    onSuccess: (server) => {
      queryClient.setQueryData(
        queryKeys.integrations.detail(workspaceId, installedServerId),
        server
      );
      void queryClient.invalidateQueries({
        queryKey: queryKeys.integrations.installed(workspaceId),
      });
    },
    onError: () => toast.error("Could not save — try again."),
  });
}

export function useUninstall(workspaceId: string) {
  const invalidate = useInvalidateIntegrations(workspaceId);
  return useMutation({
    mutationFn: (installedServerId: string) => uninstallAction(workspaceId, installedServerId),
    onSuccess: () => {
      invalidate();
      toast.success("Integration removed. Its call history is kept.");
    },
    onError: () => toast.error("Could not remove the integration — try again."),
  });
}

export function usePutCredential(workspaceId: string, installedServerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PutCredentialRequest) =>
      putCredentialAction(workspaceId, installedServerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.integrations.credentials(workspaceId, installedServerId),
      });
      // Writing a credential can flip a pending server to active, so the
      // detail and list views both need refreshing.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.integrations.detail(workspaceId, installedServerId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.integrations.installed(workspaceId),
      });
      toast.success("Credential saved. It is encrypted and cannot be read back.");
    },
    onError: () => toast.error("Could not save the credential — try again."),
  });
}

/**
 * Starts an OAuth2 connection. The mutation's only job is to hand back
 * `authorization_url` for the caller to navigate to — there is nothing
 * to invalidate yet, because nothing changes until the provider's
 * callback lands and the server flips from `pending_auth` to `active`.
 */
export function useStartOauth(workspaceId: string, installedServerId: string) {
  return useMutation({
    mutationFn: () => startOauthAction(workspaceId, installedServerId),
    onError: () => toast.error("Could not start the connection — try again."),
  });
}

export function useDeleteCredential(workspaceId: string, installedServerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => deleteCredentialAction(workspaceId, installedServerId, key),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.integrations.credentials(workspaceId, installedServerId),
      });
    },
    onError: () => toast.error("Could not delete the credential — try again."),
  });
}

export function useGrantPermission(workspaceId: string, installedServerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GrantPermissionRequest) =>
      grantPermissionAction(workspaceId, installedServerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["workspaces", workspaceId, "integrations", installedServerId, "permissions"],
      });
      toast.success("Access granted.");
    },
    onError: () => toast.error("Could not grant access — try again."),
  });
}

export function useRevokePermission(workspaceId: string, installedServerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (permissionId: string) =>
      revokePermissionAction(workspaceId, installedServerId, permissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["workspaces", workspaceId, "integrations", installedServerId, "permissions"],
      });
    },
    onError: () => toast.error("Could not revoke access — try again."),
  });
}
