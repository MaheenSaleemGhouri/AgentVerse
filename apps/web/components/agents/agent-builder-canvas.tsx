"use client";

import { Bot, Wrench } from "lucide-react";

import type { Agent, AgentVersion } from "@/lib/api/agents";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";

/**
 * Phase 4 ships single-agent-with-tools only — this renders that one
 * node on a canvas-styled surface (dot-grid, pan-free) rather than
 * pulling in a full graph-editor library for a graph with one node.
 * Multi-node layout/connections are Phase 10's DAG workflow builder.
 */
export function AgentBuilderCanvas({
  agent,
  version,
}: {
  agent: Agent;
  version: AgentVersion;
}): React.JSX.Element {
  return (
    <div
      className="relative flex h-full min-h-[420px] items-center justify-center overflow-hidden rounded-xl border border-border bg-secondary/40"
      style={{
        backgroundImage:
          "radial-gradient(color-mix(in oklab, var(--border) 140%, transparent) 1px, transparent 1px)",
        backgroundSize: "20px 20px",
      }}
    >
      <div className="flex w-72 flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="flex size-9 items-center justify-center rounded-md bg-accent text-accent-foreground">
            <Bot className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{agent.name}</p>
            <p className="truncate text-xs text-muted-foreground">{version.model}</p>
          </div>
          <AgentStatusBadge status={agent.status} />
        </div>
        <p className="line-clamp-3 text-sm text-muted-foreground">{version.system_instructions}</p>
        {version.tools.length > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Wrench className="size-3.5" />
            {version.tools.length} tool{version.tools.length === 1 ? "" : "s"} enabled
          </div>
        )}
      </div>
    </div>
  );
}
