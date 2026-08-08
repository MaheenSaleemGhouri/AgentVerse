"use client";

import { PackageSearch, Search } from "lucide-react";
import * as React from "react";

import {
  CATALOG_PAGE_SIZE,
  type Category,
  type ListingPage,
} from "@/lib/marketplace/types";
import { useCatalog } from "@/lib/queries/marketplace";
import { useDebounced } from "@/lib/queries/search";

import { ListingCard } from "@/components/marketplace/listing-card";
import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { FilterGroup } from "@/components/patterns/filter-group";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

type Source = "all" | "official" | "community";
type Sort = "popular" | "newest" | "rating" | "name";

const SOURCES: ReadonlyArray<{ value: Source; label: string }> = [
  { value: "all", label: "All" },
  { value: "official", label: "Templates" },
  { value: "community", label: "Community" },
];

const SORTS: ReadonlyArray<{ value: Sort; label: string }> = [
  { value: "popular", label: "Popular" },
  { value: "newest", label: "Newest" },
  { value: "rating", label: "Top rated" },
  { value: "name", label: "A–Z" },
];

/**
 * The catalog: search, filter, page.
 *
 * Filter state is local rather than in the URL. The catalog is a
 * browsing surface — you scan it, open one listing, and come back — and
 * a listing's own URL is the thing worth sharing. Pushing a query string
 * on every keystroke would fill the back stack with states nobody wants
 * to return to.
 *
 * "Templates" is the official filter rather than a separate page: the
 * first-party library and community listings are the same kind of thing,
 * install the same way, and a reader deciding between them should not
 * have to navigate to compare.
 */
export function MarketplaceCatalog({
  workspaceId,
  categories,
  initialPage,
}: {
  workspaceId: string;
  categories: Category[];
  initialPage: ListingPage;
}): React.JSX.Element {
  const [rawQuery, setRawQuery] = React.useState("");
  const [category, setCategory] = React.useState<string>("all");
  const [source, setSource] = React.useState<Source>("all");
  const [sort, setSort] = React.useState<Sort>("popular");
  const [page, setPage] = React.useState(1);

  const query = useDebounced(rawQuery.trim());

  // Any filter change invalidates the current page number — staying on
  // page 3 of a result set that now has one page shows an empty grid
  // and looks like "no results".
  React.useEffect(() => {
    setPage(1);
  }, [query, category, source, sort]);

  const filters = {
    ...(query ? { q: query } : {}),
    ...(category === "all" ? {} : { category }),
    ...(source === "all" ? {} : { official: source === "official" }),
    sort,
    page,
  };

  const untouched = query === "" && category === "all" && source === "all" && sort === "popular";

  const { data, isPending, isError, refetch } = useCatalog(
    filters,
    // Only the server-rendered first view can be seeded; any other
    // filter combination is genuinely a different query.
    untouched && page === 1 ? initialPage : undefined,
  );

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / CATALOG_PAGE_SIZE));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative lg:max-w-sm lg:flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            value={rawQuery}
            onChange={(event) => setRawQuery(event.target.value)}
            placeholder="Search the marketplace…"
            aria-label="Search the marketplace"
            // The API caps `q` at 200 and 422s past it. Capping the
            // input instead means a long paste searches its first 200
            // characters rather than erroring under the search box.
            maxLength={200}
            className="pl-9"
          />
        </div>
        <FilterGroup label="Filter by source" value={source} onValueChange={setSource} options={SOURCES} />
        <FilterGroup
          label="Sort listings"
          value={sort}
          onValueChange={setSort}
          options={SORTS}
          className="lg:ml-auto"
        />
      </div>

      <FilterGroup
        label="Filter by category"
        value={category}
        onValueChange={setCategory}
        options={[
          { value: "all", label: "All categories" },
          ...categories.map((entry) => ({ value: entry.slug, label: entry.name })),
        ]}
      />

      {isError ? (
        <ErrorState
          title="Could not load the marketplace"
          description="The catalog service did not respond."
          onRetry={() => void refetch()}
        />
      ) : isPending ? (
        <CatalogSkeleton />
      ) : data.data.length === 0 ? (
        <EmptyState
          icon={PackageSearch}
          title={query ? `Nothing matched “${query}”` : "Nothing here yet"}
          description={
            query
              ? "Try fewer words, or clear the filters to see the whole catalog."
              : "No published listings in this category yet."
          }
          action={
            untouched ? undefined : (
              <Button
                variant="outline"
                onClick={() => {
                  setRawQuery("");
                  setCategory("all");
                  setSource("all");
                  setSort("popular");
                }}
              >
                Clear filters
              </Button>
            )
          }
        />
      ) : (
        <>
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {data.total} {data.total === 1 ? "listing" : "listings"}
          </p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.data.map((listing) => (
              <ListingCard key={listing.slug} workspaceId={workspaceId} listing={listing} />
            ))}
          </div>

          {totalPages > 1 && (
            <nav
              aria-label="Catalog pages"
              className="flex items-center justify-center gap-3 pt-2"
            >
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

/** Matches the card's real height, so arriving data does not shift the
 * page under the reader's cursor. */
function CatalogSkeleton(): React.JSX.Element {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }, (_, index) => (
        <Card key={index} className="gap-0 p-5">
          <div className="flex items-start gap-3">
            <Skeleton className="size-9 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-1.5 h-3 w-4/5" />
          <Skeleton className="mt-4 h-3 w-24" />
        </Card>
      ))}
    </div>
  );
}
