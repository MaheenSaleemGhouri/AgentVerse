"use client";

import { ShieldCheck, Trash2, Users } from "lucide-react";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { InstalledServer, PermissionLevel } from "@/lib/api/integrations";
import { PERMISSION_LEVELS } from "@/lib/integrations-vocabulary";
import { useGrantPermission, usePermissions, useRevokePermission } from "@/lib/queries/integrations";
import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/patterns/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const LEVELS: readonly PermissionLevel[] = ["read_only", "read_write", "admin"];

/**
 * Which agents may use this server, and which of its tools.
 *
 * The tool picker matters more than it looks: an empty selection means
 * *every* tool, and the copy says so rather than leaving the user to
 * infer it from an unchecked list. Mutating tools are marked, because
 * granting read-write is the decision worth being deliberate about.
 */
export function PermissionsPanel({
  workspaceId,
  server,
  agents,
}: {
  workspaceId: string;
  server: InstalledServer;
  agents: Agent[];
}): React.JSX.Element {
  const { data, isLoading } = usePermissions(workspaceId, server.id);
  const grant = useGrantPermission(workspaceId, server.id);
  const revoke = useRevokePermission(workspaceId, server.id);

  const [agentId, setAgentId] = React.useState("");
  const [level, setLevel] = React.useState<PermissionLevel>("read_only");
  const [selectedTools, setSelectedTools] = React.useState<string[]>([]);

  const agentsById = React.useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent])),
    [agents]
  );

  function toggleTool(name: string): void {
    setSelectedTools((current) =>
      current.includes(name) ? current.filter((tool) => tool !== name) : [...current, name]
    );
  }

  function onGrant(): void {
    grant.mutate(
      {
        agent_id: agentId || null,
        team_id: null,
        level,
        allowed_tools: selectedTools,
        timeout_seconds: 30,
        max_retries: 2,
        cache_ttl_seconds: 0,
        max_calls_per_run: 50,
        priority: 0,
      },
      {
        onSuccess: () => {
          setAgentId("");
          setSelectedTools([]);
        },
      }
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {isLoading ? (
        <Skeleton className="h-24 rounded-lg" />
      ) : (data ?? []).length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No agent can use this yet"
          description="Grant an agent access below. Until then its tools are not offered to anything."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {(data ?? []).map((permission) => {
            const meta = PERMISSION_LEVELS[permission.level];
            const LevelIcon = meta.icon;
            const agent = permission.agent_id
              ? agentsById.get(permission.agent_id)
              : undefined;

            return (
              <li
                key={permission.id}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3"
              >
                <LevelIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {agent?.name ??
                      (permission.agent_id
                        ? permission.agent_id.slice(0, 8)
                        : permission.team_id
                          ? `Team ${permission.team_id.slice(0, 8)}`
                          : "Every agent in this workspace")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {meta.label} ·{" "}
                    {permission.allowed_tools.length === 0
                      ? "all tools"
                      : `${permission.allowed_tools.length} of ${server.tools.length} tools`}{" "}
                    · up to {permission.max_calls_per_run} calls per run
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Revoke access"
                  onClick={() => revoke.mutate(permission.id)}
                >
                  <Trash2 />
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      <Card className="gap-4 p-5">
        <h3 className="text-sm font-medium">Grant access</h3>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="grant-agent">Agent</Label>
            <Select value={agentId} onValueChange={setAgentId}>
              <SelectTrigger id="grant-agent">
                <SelectValue placeholder="Every agent in this workspace" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Leave empty to grant every agent in the workspace.
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="grant-level">Access level</Label>
            <Select value={level} onValueChange={(next) => setLevel(next as PermissionLevel)}>
              <SelectTrigger id="grant-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {PERMISSION_LEVELS[option].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {PERMISSION_LEVELS[level].summary}
            </p>
          </div>
        </div>

        {server.tools.length > 0 && (
          <fieldset className="grid gap-2">
            <legend className="mb-1.5 text-sm font-medium">Tools</legend>
            <p className="text-xs text-muted-foreground">
              {selectedTools.length === 0
                ? "Nothing selected — the agent gets every tool this server offers."
                : `${selectedTools.length} selected. Only these will be available.`}
            </p>
            <div className="mt-1 grid max-h-60 gap-1.5 overflow-y-auto rounded-md border border-border p-3 sm:grid-cols-2">
              {server.tools.map((tool) => {
                const disabledByLevel = tool.is_mutating && level === "read_only";
                return (
                  <label
                    key={tool.name}
                    className={cn(
                      "flex items-start gap-2 rounded p-1.5 text-sm",
                      disabledByLevel && "opacity-50"
                    )}
                  >
                    <Checkbox
                      checked={selectedTools.includes(tool.name)}
                      onCheckedChange={() => toggleTool(tool.name)}
                      aria-describedby={`tool-${tool.name}-desc`}
                    />
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <code className="font-mono text-xs">{tool.name}</code>
                        {tool.is_mutating && (
                          <Badge variant="outline" className="text-warning">
                            writes
                          </Badge>
                        )}
                      </span>
                      <span
                        id={`tool-${tool.name}-desc`}
                        className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground"
                      >
                        {disabledByLevel
                          ? "Refused at read-only access."
                          : tool.description || "No description provided by the server."}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        )}

        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Users className="size-3.5" aria-hidden="true" />
            Every call is logged, whether it succeeds or is refused.
          </p>
          <Button onClick={onGrant} disabled={grant.isPending}>
            {grant.isPending ? "Granting…" : "Grant access"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
