"use client";

import { Search } from "lucide-react";
import { useState } from "react";

import { searchKnowledgeBaseAction } from "@/lib/api/actions";
import type { SearchResponse } from "@/lib/api/knowledge";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Runs the exact retrieval pipeline an agent run uses, so what is shown
 * here is what the agent will actually see. Each hit exposes its fusion
 * score and the rank each arm gave it — "why did this chunk surface?"
 * has to be answerable, or this is a debugging tool that can't debug.
 */
export function SearchPreview({
  workspaceId,
  knowledgeBaseId,
}: {
  workspaceId: string;
  knowledgeBaseId: string;
}): React.JSX.Element {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    setError(null);
    try {
      setResult(await searchKnowledgeBaseAction(workspaceId, knowledgeBaseId, query.trim()));
    } catch {
      setResult(null);
      setError(
        "Search is unavailable right now. If you recently changed embedding models, reindex this knowledge base."
      );
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={(e) => void onSubmit(e)} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask what your agent would ask…"
          aria-label="Test retrieval query"
          maxLength={2000}
        />
        <Button type="submit" disabled={isSearching || query.trim().length === 0}>
          <Search />
          {isSearching ? "Searching…" : "Test retrieval"}
        </Button>
      </form>

      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive-soft px-3 py-2 text-sm text-destructive-strong">
          {error}
        </p>
      )}

      {result && result.hits.length === 0 && (
        <div className="rounded-xl border border-dashed border-border py-10 text-center">
          <p className="font-medium">Nothing matched</p>
          <p className="text-sm text-muted-foreground">
            Your agent would answer this question without any documents. Try different wording, or
            upload a document that covers it.
          </p>
        </div>
      )}

      {result && result.hits.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            {result.hits.length} chunks · {result.used_tokens} of {result.budget_tokens} context
            tokens used
            {result.dropped_chunk_count > 0 && ` · ${result.dropped_chunk_count} dropped for size`}
          </p>
          {result.hits.map((hit) => (
            <article key={hit.chunk_id} className="rounded-lg border border-border px-4 py-3">
              <header className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Chunk {hit.chunk_index}</span>
                <span>score {hit.score.toFixed(4)}</span>
                <span>
                  {hit.vector_rank !== null ? `semantic #${hit.vector_rank}` : "semantic —"}
                </span>
                <span>
                  {hit.keyword_rank !== null ? `keyword #${hit.keyword_rank}` : "keyword —"}
                </span>
              </header>
              <p className="mt-2 whitespace-pre-wrap text-sm">{hit.content}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
