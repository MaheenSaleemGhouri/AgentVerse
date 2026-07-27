"use client";

import { Library } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listKnowledgeBasesAction } from "@/lib/api/actions";
import type { KnowledgeBase } from "@/lib/api/knowledge";

import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";

const MAX_ATTACHED = 10;

/**
 * Attaches knowledge bases to the agent version being edited.
 *
 * The selection is part of the *versioned* config, not a live link: a
 * published version keeps grounding in exactly the knowledge bases it
 * was published with, so changing this and saving produces a new
 * version rather than silently altering a running agent's behaviour.
 */
export function KnowledgeBaseAttach({
  workspaceId,
  value,
  onChange,
}: {
  workspaceId: string;
  value: string[];
  onChange: (next: string[]) => void;
}): React.JSX.Element {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void listKnowledgeBasesAction(workspaceId)
      .then((bases) => {
        if (!cancelled) setKnowledgeBases(bases);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  if (loadFailed) {
    return (
      <p className="text-sm text-destructive">
        Could not load knowledge bases. Reload the builder to try again.
      </p>
    );
  }

  if (knowledgeBases === null) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    );
  }

  if (knowledgeBases.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center">
        <span className="mx-auto mb-2 flex size-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Library className="size-5" aria-hidden="true" />
        </span>
        <p className="font-medium">No knowledge bases yet</p>
        <p className="text-sm text-muted-foreground">
          <Link
            href={`/dashboard/${workspaceId}/knowledge`}
            className="underline underline-offset-4"
          >
            Create one
          </Link>{" "}
          and upload a document to ground this agent&apos;s answers.
        </p>
      </div>
    );
  }

  const atLimit = value.length >= MAX_ATTACHED;

  return (
    <div className="flex flex-col gap-3">
      {knowledgeBases.map((kb) => {
        const attached = value.includes(kb.id);
        return (
          <div
            key={kb.id}
            className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"
          >
            <div className="min-w-0">
              <p className="font-medium">{kb.name}</p>
              <p className="truncate text-sm text-muted-foreground">
                {kb.description ?? kb.embedding_model}
              </p>
            </div>
            <Switch
              checked={attached}
              // Disabled only when adding *another* would exceed the cap
              // — an already-attached one must always be removable.
              disabled={!attached && atLimit}
              onCheckedChange={(next) => {
                onChange(next ? [...value, kb.id] : value.filter((id) => id !== kb.id));
              }}
              aria-label={`Attach ${kb.name}`}
            />
          </div>
        );
      })}
      {atLimit && (
        <p className="text-xs text-muted-foreground">
          An agent can be grounded in up to {MAX_ATTACHED} knowledge bases.
        </p>
      )}
    </div>
  );
}
