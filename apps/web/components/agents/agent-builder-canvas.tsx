"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, BookOpen, Bot, MessageSquare, Sparkles, Wrench } from "lucide-react";
import * as React from "react";

import type { Agent, AgentVersion } from "@/lib/api/agents";
import type { KnowledgeBase } from "@/lib/api/knowledge";
import { BUILTIN_TOOLS } from "@/lib/validation/agent-config";
import { cn } from "@/lib/utils";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";

/**
 * The builder canvas for Phase 4's one supported topology:
 * single-agent-with-tools.
 *
 * Rendered as a real graph — input → agent → output, with knowledge and
 * tools as attached nodes — rather than one card on a dot grid, because
 * the shape of the graph is what the user is actually configuring. It is
 * deliberately *not* a general-purpose graph editor: multi-node layout,
 * dragging, and connections are Phase 10's DAG workflow builder, and
 * pulling a canvas library in now for a fixed three-node graph would be
 * weight every builder page pays for nothing (Rule 10).
 *
 * Nodes highlight when their corresponding config tab is active, so the
 * canvas and the panel read as one surface rather than two.
 */
export function AgentBuilderCanvas({
  agent,
  version,
  knowledgeBases,
  activeTab,
}: {
  agent: Agent;
  version: AgentVersion;
  knowledgeBases: KnowledgeBase[];
  activeTab: string;
}): React.JSX.Element {
  const reduceMotion = useReducedMotion();
  const attachedCount = version.knowledge_base_ids.length;
  const attachedNames = knowledgeBases
    .filter((kb) => version.knowledge_base_ids.includes(kb.id))
    .map((kb) => kb.name);

  const enter = reduceMotion
    ? {}
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

  return (
    <div
      className="relative flex min-h-[440px] flex-col items-center justify-center gap-4 overflow-hidden rounded-xl border border-border bg-secondary/30 p-6"
      style={{
        backgroundImage:
          "radial-gradient(color-mix(in oklab, var(--border) 140%, transparent) 1px, transparent 1px)",
        backgroundSize: "20px 20px",
      }}
    >
      <div className="flex w-full max-w-md flex-col items-center gap-3">
        <motion.div {...enter} transition={{ duration: 0.25 }} className="w-full">
          <CanvasNode
            icon={MessageSquare}
            label="Input"
            detail="The user's prompt"
            muted
          />
        </motion.div>

        <Connector />

        <motion.div
          {...enter}
          transition={{ duration: 0.25, delay: reduceMotion ? 0 : 0.05 }}
          className={cn(
            "w-full rounded-xl border bg-card p-4 shadow-sm transition-colors",
            activeTab === "instructions" || activeTab === "model"
              ? "border-primary/60 ring-2 ring-primary/15"
              : "border-border"
          )}
        >
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
            >
              <Bot className="size-4.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{agent.name}</p>
              <p className="truncate font-mono text-xs text-muted-foreground">{version.model}</p>
            </div>
            <AgentStatusBadge status={agent.status} />
          </div>

          <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">
            {version.system_instructions}
          </p>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <AttachedNode
              icon={BookOpen}
              label="Knowledge"
              value={
                attachedCount === 0
                  ? "None attached"
                  : attachedNames.slice(0, 2).join(", ") +
                    (attachedCount > 2 ? ` +${attachedCount - 2}` : "")
              }
              isActive={activeTab === "knowledge"}
              isEmpty={attachedCount === 0}
            />
            <AttachedNode
              icon={Wrench}
              label="Tools"
              value={
                version.tools.length === 0
                  ? "None enabled"
                  : version.tools
                      .map(
                        (id) => BUILTIN_TOOLS.find((tool) => tool.id === id)?.label ?? id
                      )
                      .join(", ")
              }
              isActive={activeTab === "tools"}
              isEmpty={version.tools.length === 0}
            />
          </div>
        </motion.div>

        <Connector />

        <motion.div
          {...enter}
          transition={{ duration: 0.25, delay: reduceMotion ? 0 : 0.1 }}
          className="w-full"
        >
          <CanvasNode
            icon={Sparkles}
            label="Output"
            detail={attachedCount > 0 ? "Answer with citations" : "Answer"}
            muted
          />
        </motion.div>
      </div>

      <p className="absolute right-4 bottom-3 text-xs text-muted-foreground">
        Single agent with tools · Phase 4 topology
      </p>
    </div>
  );
}

function Connector(): React.JSX.Element {
  return (
    <span aria-hidden="true" className="flex flex-col items-center text-border">
      <span className="h-4 w-px bg-border" />
      <ArrowRight className="size-3 rotate-90 text-muted-foreground/60" />
    </span>
  );
}

function CanvasNode({
  icon: Icon,
  label,
  detail,
  muted,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  detail: string;
  muted?: boolean;
}): React.JSX.Element {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-lg border border-border px-3 py-2.5",
        muted ? "bg-card/60" : "bg-card"
      )}
    >
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground"
      >
        <Icon className="size-3.5" />
      </span>
      <span className="text-sm font-medium">{label}</span>
      <span className="ml-auto truncate text-xs text-muted-foreground">{detail}</span>
    </div>
  );
}

function AttachedNode({
  icon: Icon,
  label,
  value,
  isActive,
  isEmpty,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  isActive: boolean;
  isEmpty: boolean;
}): React.JSX.Element {
  return (
    <div
      className={cn(
        "rounded-lg border px-2.5 py-2 transition-colors",
        isActive ? "border-primary/60 bg-accent/40" : "border-border bg-muted/40"
      )}
    >
      <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon className="size-3" aria-hidden="true" />
        {label}
      </span>
      <p
        className={cn(
          "mt-0.5 truncate text-xs",
          isEmpty ? "text-muted-foreground/70 italic" : "text-foreground"
        )}
      >
        {value}
      </p>
    </div>
  );
}
