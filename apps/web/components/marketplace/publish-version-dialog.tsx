"use client";

import { Upload } from "lucide-react";
import * as React from "react";

import { getLatestVersionAction } from "@/lib/api/actions";
import type { Agent } from "@/lib/api/agents";
import type { Listing } from "@/lib/marketplace/types";
import { usePublishVersion } from "@/lib/queries/marketplace";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

/**
 * Publish one of this workspace's agents as a version of a listing.
 *
 * The published artifact is the agent's **latest published version**, not
 * the agent — a listing version is a frozen copy, so that installing it
 * next month produces what the publisher reviewed today rather than
 * whatever the agent has drifted into.
 *
 * `knowledge_base_ids` is deliberately not carried across. It names the
 * publisher's knowledge bases, and there is nothing in an installing
 * workspace to remap them to; the API's sanitizer drops it regardless,
 * and the dialog says so rather than letting a publisher assume their
 * documents travel with the listing.
 */
export function PublishVersionDialog({
  workspaceId,
  listing,
  agents,
}: {
  workspaceId: string;
  listing: Listing;
  agents: Agent[];
}): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const [agentId, setAgentId] = React.useState("");
  const [changelog, setChangelog] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const publish = usePublishVersion(workspaceId);

  const publishable = agents.filter((agent) => agent.status === "published");

  async function onPublish(): Promise<void> {
    setError(null);
    const version = await getLatestVersionAction(workspaceId, agentId);
    if (!version) {
      setError("That agent has no published version yet. Publish it first.");
      return;
    }

    await publish.mutateAsync({
      slug: listing.slug,
      body: {
        config: {
          model: version.model,
          system_instructions: version.system_instructions,
          temperature: version.temperature,
          max_output_tokens: version.max_output_tokens,
          tools: version.tools,
        },
        changelog: changelog.trim(),
        source_agent_version_id: version.id,
      },
    });
    setOpen(false);
    setChangelog("");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Upload className="size-4" />
          Publish version
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Publish a version of “{listing.title}”</DialogTitle>
          <DialogDescription>
            Freezes one of your published agents into a version people can install. Your
            knowledge bases and integration credentials do not travel with it.
          </DialogDescription>
        </DialogHeader>

        {publishable.length === 0 ? (
          <p className="rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-sm">
            You have no published agents. Publish an agent first — a draft cannot be listed.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="publish-agent">Agent</Label>
              <Select value={agentId} onValueChange={setAgentId}>
                <SelectTrigger id="publish-agent">
                  <SelectValue placeholder="Choose a published agent" />
                </SelectTrigger>
                <SelectContent>
                  {publishable.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="publish-changelog">What changed</Label>
              <Textarea
                id="publish-changelog"
                value={changelog}
                onChange={(event) => setChangelog(event.target.value)}
                placeholder="Tightened the instructions so it stops inventing changes that are not in the input."
                maxLength={2000}
                rows={3}
              />
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            disabled={agentId === "" || publish.isPending || publishable.length === 0}
            onClick={() => void onPublish()}
          >
            {publish.isPending ? "Publishing…" : "Publish version"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
