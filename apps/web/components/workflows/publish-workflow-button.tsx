"use client";

import { Rocket } from "lucide-react";
import * as React from "react";

import { usePublishWorkflow } from "@/lib/queries/workflows";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Publishing points `workflows.published_version_id` at an explicit
 * version (unlike `agents.publish`, which only ever publishes the
 * latest — this phase's rollback capability, docs/adr/0016). The button
 * always targets the current latest saved version; publishing an older
 * one is a deliberate rollback action this phase does not expose a
 * control for yet — no acceptance criterion asked for it.
 */
export function PublishWorkflowButton({
  workspaceId,
  workflowId,
  status,
  latestVersionId,
  publishedVersionId,
}: {
  workspaceId: string;
  workflowId: string;
  status: string;
  latestVersionId: string;
  publishedVersionId: string | null;
}): React.JSX.Element {
  const publish = usePublishWorkflow(workspaceId, workflowId);
  const isCurrentVersionPublished =
    status === "active" && publishedVersionId === latestVersionId;

  if (isCurrentVersionPublished) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0}>
            <Button variant="outline" disabled>
              <Rocket />
              Published
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          This version is live. Save a change to publish an updated one.
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <Button onClick={() => publish.mutate(latestVersionId)} disabled={publish.isPending}>
      <Rocket />
      {publish.isPending ? "Publishing…" : "Publish"}
    </Button>
  );
}
