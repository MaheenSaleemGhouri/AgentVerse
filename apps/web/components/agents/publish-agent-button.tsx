"use client";

import { Rocket } from "lucide-react";
import * as React from "react";

import { usePublishAgent } from "@/lib/queries/agents";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Publishing is what makes an agent runnable — an unpublished agent's
 * run submission is rejected with 409 by the API. The disabled state on
 * an already-published agent carries a tooltip explaining *why* it is
 * disabled, rather than being an inert grey button.
 */
export function PublishAgentButton({
  workspaceId,
  agentId,
  status,
}: {
  workspaceId: string;
  agentId: string;
  status: string;
}): React.JSX.Element {
  const publish = usePublishAgent(workspaceId, agentId);
  const isPublished = status === "active";

  if (isPublished) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {/* `span` wrapper: a disabled button emits no pointer events,
              so the tooltip would never open without it. */}
          <span tabIndex={0}>
            <Button variant="outline" disabled>
              <Rocket />
              Published
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          Already published. Saving a change creates a new version to publish.
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Button onClick={() => publish.mutate()} disabled={publish.isPending}>
      <Rocket />
      {publish.isPending ? "Publishing…" : "Publish"}
    </Button>
  );
}
