"use client";

import { Plug, Server } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { InstalledServer } from "@/lib/api/integrations";
import { formatRelativeTime } from "@/lib/format";
import { HEALTH, INSTALL_STATUS, TRANSPORTS } from "@/lib/integrations-vocabulary";
import { needsAttention, useInstalledServers } from "@/lib/queries/integrations";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Connected services, with the ones needing attention surfaced first.
 *
 * A server that is installed but unusable — waiting on credentials, or
 * unreachable — is the state a user most needs to see, and burying it in
 * a list sorted by name is how it stays broken.
 */
export function ConnectionsList({
  workspaceId,
  initialServers,
}: {
  workspaceId: string;
  initialServers: InstalledServer[];
}): React.JSX.Element {
  const { data, isLoading, isError, refetch } = useInstalledServers(workspaceId, initialServers);

  const { attention, healthy } = React.useMemo(() => {
    const servers = data ?? [];
    return {
      attention: servers.filter(needsAttention),
      healthy: servers.filter((server) => !needsAttention(server)),
    };
  }, [data]);

  if (isError) {
    return (
      <ErrorState
        title="Could not load your integrations"
        description="The orchestration service did not respond. Your integrations are unaffected."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading && !data) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} className="h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  if ((data ?? []).length === 0) {
    return (
      <EmptyState
        icon={Plug}
        title="No integrations yet"
        description="Install one from the marketplace, or register your own MCP server, to give your agents tools."
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {attention.length > 0 && (
        <section className="flex flex-col gap-3">
          <Alert tone="warning">
            <AlertTitle>
              {attention.length} {attention.length === 1 ? "integration needs" : "integrations need"}{" "}
              attention
            </AlertTitle>
            <AlertDescription>
              Agents cannot use these until they are resolved. Their tools are simply absent from
              a run rather than causing it to fail.
            </AlertDescription>
          </Alert>
          {attention.map((server) => (
            <ConnectionRow key={server.id} workspaceId={workspaceId} server={server} />
          ))}
        </section>
      )}

      {healthy.length > 0 && (
        <section className="flex flex-col gap-2">
          {attention.length > 0 && (
            <h2 className="text-sm font-medium text-muted-foreground">Working</h2>
          )}
          {healthy.map((server) => (
            <ConnectionRow key={server.id} workspaceId={workspaceId} server={server} />
          ))}
        </section>
      )}
    </div>
  );
}

function ConnectionRow({
  workspaceId,
  server,
}: {
  workspaceId: string;
  server: InstalledServer;
}): React.JSX.Element {
  const status = INSTALL_STATUS[server.status];
  const health = HEALTH[server.health];
  const transport = TRANSPORTS[server.transport];
  const StatusIcon = status.icon;

  return (
    <Card className="flex flex-wrap items-center gap-3 p-4">
      <span
        aria-hidden="true"
        className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
      >
        <Server className="size-4.5" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/dashboard/${workspaceId}/integrations/${server.id}`}
            className="truncate font-medium hover:underline"
          >
            {server.display_name}
          </Link>
          <StatusBadge tone={status.tone}>
            <StatusIcon className="size-3" aria-hidden="true" />
            {status.label}
          </StatusBadge>
          {server.health !== "unknown" && (
            <StatusBadge tone={health.tone}>{health.label}</StatusBadge>
          )}
          {server.mcp_server_id === null && (
            <span className="text-xs text-muted-foreground">Custom</span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {server.last_error ? server.last_error : status.summary}
        </p>
      </div>

      <div className="hidden text-right sm:block">
        <p className="text-xs text-muted-foreground">{transport.label}</p>
        <p className="text-xs text-muted-foreground">
          {server.tools.length} {server.tools.length === 1 ? "tool" : "tools"}
          {server.tools_discovered_at
            ? ` · ${formatRelativeTime(server.tools_discovered_at)}`
            : ""}
        </p>
      </div>

      <Button variant="ghost" size="sm" asChild>
        <Link href={`/dashboard/${workspaceId}/integrations/${server.id}`}>Manage</Link>
      </Button>
    </Card>
  );
}
