"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { type DocsSearchEntry, searchDocs } from "@/lib/docs/match";
import { Input } from "@/components/ui/input";

/**
 * Search across the guides, entirely in the browser.
 *
 * The whole index arrives with the page — a few dozen public guides,
 * identical for every reader — so there is nothing to fetch and nothing
 * to debounce. Matching a keystroke is a filter over an array.
 */
export function DocsSearch({ index }: { index: readonly DocsSearchEntry[] }): React.JSX.Element {
  const [query, setQuery] = React.useState("");
  const inputId = React.useId();
  const resultsId = React.useId();

  const results = React.useMemo(() => searchDocs(index, query), [index, query]);
  const searching = query.trim().length > 0;

  return (
    <div className="relative">
      <label htmlFor={inputId} className="sr-only">
        Search the documentation
      </label>
      <Search
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        id={inputId}
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search the docs…"
        className="pl-9"
        role="combobox"
        aria-expanded={searching}
        aria-controls={resultsId}
        aria-autocomplete="list"
      />

      {searching && (
        <div
          id={resultsId}
          role="listbox"
          aria-label="Search results"
          className="absolute z-20 mt-2 w-full overflow-hidden rounded-lg border border-border bg-popover shadow-lg"
        >
          {results.length === 0 ? (
            <p className="px-3 py-4 text-sm text-muted-foreground">
              Nothing matched “{query}”.
            </p>
          ) : (
            <ul>
              {results.map((entry) => (
                <li key={entry.slug} role="option" aria-selected={false}>
                  <Link
                    href={`/docs/${entry.slug}`}
                    onClick={() => setQuery("")}
                    className="block px-3 py-2 hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                  >
                    <span className="block text-sm font-medium">{entry.title}</span>
                    <span className="block text-xs text-muted-foreground">
                      {entry.pillarName} · {entry.summary}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Announced to screen readers without stealing focus, so someone
          navigating by keyboard hears that results changed. */}
      <p aria-live="polite" className="sr-only">
        {searching ? `${String(results.length)} results for ${query}` : ""}
      </p>
    </div>
  );
}
