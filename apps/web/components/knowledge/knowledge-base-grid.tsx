"use client";

import { BookOpen, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { KnowledgeBase } from "@/lib/api/knowledge";
import { formatRelativeTime } from "@/lib/format";
import { useKnowledgeBases } from "@/lib/queries/knowledge";

import { CreateKnowledgeBaseDialog } from "@/components/knowledge/create-knowledge-base-dialog";
import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

export function KnowledgeBaseGrid({
  workspaceId,
  initialKnowledgeBases,
}: {
  workspaceId: string;
  initialKnowledgeBases: KnowledgeBase[];
}): React.JSX.Element {
  const { data, isLoading, isError, refetch } = useKnowledgeBases(
    workspaceId,
    initialKnowledgeBases
  );
  const [query, setQuery] = React.useState("");

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return data ?? [];
    return (data ?? []).filter(
      (kb) =>
        kb.name.toLowerCase().includes(needle) ||
        (kb.description ?? "").toLowerCase().includes(needle)
    );
  }, [data, query]);

  if (isError) {
    return (
      <ErrorState
        title="Could not load knowledge bases"
        description="The knowledge API did not respond. Your session may have expired."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading && !data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-40 rounded-xl" />
        ))}
      </div>
    );
  }

  if ((data ?? []).length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No knowledge bases yet"
        description="A knowledge base is a collection of documents your agents retrieve from and cite. Create one, upload a file, then attach it to an agent."
        action={<CreateKnowledgeBaseDialog workspaceId={workspaceId} />}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search knowledge bases…"
          aria-label="Search knowledge bases"
          className="pl-9"
        />
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No knowledge bases match"
          description="Try a different search term."
          action={
            <Button variant="outline" onClick={() => setQuery("")}>
              Clear search
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((kb) => (
            <Card
              key={kb.id}
              className="group relative gap-0 p-5 transition-[transform,border-color] duration-150 hover:-translate-y-px hover:border-primary/50 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
            >
              <div className="flex items-start gap-3">
                <span
                  aria-hidden="true"
                  className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
                >
                  <BookOpen className="size-4.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/dashboard/${workspaceId}/knowledge/${kb.id}`}
                    className="font-medium after:absolute after:inset-0 after:content-[''] hover:underline"
                  >
                    {kb.name}
                  </Link>
                  <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
                    {kb.description ?? "No description"}
                  </p>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-xs">
                  {kb.embedding_model}
                </Badge>
                <span className="ml-auto text-xs text-muted-foreground">
                  {formatRelativeTime(kb.updated_at)}
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
