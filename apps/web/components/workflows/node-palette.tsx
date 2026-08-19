"use client";

import * as React from "react";

import type { WorkflowNodeType } from "@/lib/api/workflows";
import { WORKFLOW_NODE_META } from "@/lib/workflows/node-types";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const PALETTE_TYPES: readonly WorkflowNodeType[] = [
  "agent_step",
  "team_step",
  "conditional_branch",
  "human_approval",
  "parallel_fanout",
];

/**
 * Click-to-add rather than HTML5 drag-and-drop from the palette onto the
 * canvas: it reaches the same acceptance criterion (a node vocabulary
 * the user can place) with a fraction of the interaction-handling code,
 * and the canvas already supports drag-to-reposition after placement
 * (KISS — the simplest sufficient interaction, Rule 10).
 */
export function NodePalette({
  onAdd,
}: {
  onAdd: (type: WorkflowNodeType) => void;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card/95 p-1.5 shadow-sm backdrop-blur">
      {PALETTE_TYPES.map((type) => {
        const meta = WORKFLOW_NODE_META[type];
        const Icon = meta.icon;
        return (
          <Tooltip key={type}>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Add ${meta.label}`}
                onClick={() => onAdd(type)}
              >
                <Icon />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              <p className="font-medium">{meta.label}</p>
              <p className="text-xs text-muted-foreground">{meta.description}</p>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
