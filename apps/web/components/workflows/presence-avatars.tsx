"use client";

import * as React from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "?";
  const last = parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/** A stable-per-name hue so the same collaborator always gets the same colour across a session. */
function hueFor(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) % 360;
  return hash;
}

const MAX_VISIBLE = 4;

export function PresenceAvatars({
  presence,
}: {
  presence: Map<string, { name: string; lastSeenAt: number }>;
}): React.JSX.Element | null {
  const collaborators = React.useMemo(() => [...presence.values()], [presence]);
  if (collaborators.length === 0) return null;

  const visible = collaborators.slice(0, MAX_VISIBLE);
  const overflow = collaborators.length - visible.length;

  return (
    <div className="flex items-center -space-x-2">
      {visible.map((collaborator, index) => (
        <Tooltip key={`${collaborator.name}-${index}`}>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "flex size-7 items-center justify-center rounded-full border-2 border-background text-[10px] font-semibold text-white"
              )}
              style={{ backgroundColor: `oklch(0.6 0.12 ${hueFor(collaborator.name)})` }}
              aria-hidden="true"
            >
              {initials(collaborator.name)}
            </span>
          </TooltipTrigger>
          <TooltipContent>{collaborator.name}</TooltipContent>
        </Tooltip>
      ))}
      {overflow > 0 && (
        <span className="flex size-7 items-center justify-center rounded-full border-2 border-background bg-muted text-[10px] font-semibold text-muted-foreground">
          +{overflow}
        </span>
      )}
    </div>
  );
}
