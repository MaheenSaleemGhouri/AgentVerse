"use client";

import { ArrowLeft, ExternalLink, Trash2, Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { InstalledServer } from "@/lib/api/integrations";
import { formatRelativeTime } from "@/lib/format";
import { HEALTH, INSTALL_STATUS, TRANSPORTS } from "@/lib/integrations-vocabulary";
import { useInstalledServer, useUninstall, useUpdateInstalled } from "@/lib/queries/integrations";
import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/patterns/empty-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { CredentialsPanel } from "@/components/integrations/credentials-panel";
import { PermissionsPanel } from "@/components/integrations/permissions-panel";
import { RuntimeView } from "@/components/integrations/runtime-view";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function ServerDetail({
  workspaceId,
  initialServer,
  agents,
}: {
  workspaceId: string;
  initialServer: InstalledServer;
  agents: Agent[];
}): React.JSX.Element {
  const router = useRouter();
  const { data } = useInstalledServer(workspaceId, initialServer.id, initialServer);
  const server = data ?? initialServer;
  const update = useUpdateInstalled(workspaceId, server.id);
  const uninstall = useUninstall(workspaceId);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const status = INSTALL_STATUS[server.status];
  const health = HEALTH[server.health];
  const transport = TRANSPORTS[server.transport];
  const StatusIcon = status.icon;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start gap-3">
        <Button variant="ghost" size="icon-sm" asChild aria-label="Back to integrations">
          <Link href={`/dashboard/${workspaceId}/integrations`}>
            <ArrowLeft />
          </Link>
        </Button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-lg font-semibold tracking-tight">
              {server.display_name}
            </h1>
            <StatusBadge tone={status.tone}>
              <StatusIcon className="size-3" aria-hidden="true" />
              {status.label}
            </StatusBadge>
            {server.health !== "unknown" && (
              <StatusBadge tone={health.tone}>{health.label}</StatusBadge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {transport.label} · {transport.summary}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={server.status === "active"}
              disabled={server.status === "pending_auth" || update.isPending}
              onCheckedChange={(checked) =>
                update.mutate({ status: checked ? "active" : "disabled" })
              }
              aria-label="Enabled"
            />
            Enabled
          </label>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Remove integration"
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 />
          </Button>
        </div>
      </div>

      {server.last_error && (
        <Alert tone="danger">
          <AlertDescription>{server.last_error}</AlertDescription>
        </Alert>
      )}

      {server.status === "pending_auth" && (
        <Alert tone="warning">
          <AlertDescription>
            This integration is installed but not yet usable — add its credentials below and it
            will activate automatically.
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue={server.status === "pending_auth" ? "credentials" : "tools"}>
        <TabsList>
          <TabsTrigger value="tools">Tools</TabsTrigger>
          <TabsTrigger value="credentials">Credentials</TabsTrigger>
          <TabsTrigger value="access">Access</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="tools" className="mt-5">
          {server.tools.length === 0 ? (
            <EmptyState
              icon={Wrench}
              title="No tools discovered"
              description={
                server.status === "pending_auth"
                  ? "Tools are discovered once the server can be reached. Add its credentials first."
                  : "This server did not advertise any tools when it was last contacted."
              }
            />
          ) : (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                {server.tools.length} {server.tools.length === 1 ? "tool" : "tools"}
                {server.tools_discovered_at
                  ? ` · discovered ${formatRelativeTime(server.tools_discovered_at)}`
                  : ""}
              </p>
              <ul className="grid gap-2 sm:grid-cols-2">
                {server.tools.map((tool) => (
                  <li
                    key={tool.name}
                    className={cn(
                      "rounded-lg border p-3",
                      tool.is_mutating ? "border-warning/30" : "border-border"
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="font-mono text-sm">{tool.name}</code>
                      {tool.is_mutating && (
                        <Badge variant="outline" className="text-warning">
                          writes
                        </Badge>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {tool.description || "No description provided by the server."}
                    </p>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted-foreground">
                Tools marked <strong>writes</strong> change data on the connected service. An
                agent with read-only access cannot call them.
              </p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="credentials" className="mt-5">
          <CredentialsPanel workspaceId={workspaceId} server={server} />
        </TabsContent>

        <TabsContent value="access" className="mt-5">
          <PermissionsPanel workspaceId={workspaceId} server={server} agents={agents} />
        </TabsContent>

        <TabsContent value="activity" className="mt-5">
          <RuntimeView workspaceId={workspaceId} installedServerId={server.id} />
        </TabsContent>
      </Tabs>

      {server.endpoint_url && (
        <Card className="gap-1 p-4">
          <p className="text-xs text-muted-foreground">Endpoint</p>
          <p className="flex items-center gap-1.5 font-mono text-sm break-all">
            {server.endpoint_url}
            <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          </p>
        </Card>
      )}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {server.display_name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Its tools stop being offered to every agent immediately, and its stored credentials
              are removed. The record of what it did — every tool call, including refused ones —
              is kept.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() =>
                uninstall.mutate(server.id, {
                  onSuccess: () => router.push(`/dashboard/${workspaceId}/integrations`),
                })
              }
            >
              Remove integration
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
