"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { searchWorkspaceAction } from "@/lib/api/actions";
import { MIN_SEARCH_LENGTH, NAVIGABLE_KINDS, type SearchResults } from "@/lib/search/kinds";
import { queryKeys } from "@/lib/queries/keys";

/** Long enough that a fast typist issues one request per word rather
 * than one per letter; short enough that results feel immediate. */
const DEBOUNCE_MS = 200;

export function useDebounced<T>(value: T, delay = DEBOUNCE_MS): T {
  const [debounced, setDebounced] = React.useState(value);

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

export function useWorkspaceSearch(workspaceId: string, rawQuery: string) {
  const query = useDebounced(rawQuery.trim());

  return useQuery<SearchResults>({
    queryKey: queryKeys.search(workspaceId, query),
    // Only the kinds the dashboard can open — see `NAVIGABLE_KINDS`.
    // Asking for a kind whose results cannot be navigated to would pay
    // for a query to render a dead link.
    queryFn: () => searchWorkspaceAction(workspaceId, query, NAVIGABLE_KINDS),
    // Two letters is where the server starts returning anything, so
    // below that the request is guaranteed-empty work.
    enabled: query.length >= MIN_SEARCH_LENGTH,
    // Without this the list empties on every keystroke while the next
    // request is in flight, which reads as "no results" flashing
    // between every letter of a search that is finding plenty.
    placeholderData: keepPreviousData,
    // Results for the same string do not change meaningfully within one
    // palette session, and reopening ⌘K on the same query should not
    // re-query.
    staleTime: 30_000,
  });
}
