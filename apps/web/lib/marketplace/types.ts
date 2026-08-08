import type { components } from "@agentverse/contracts";

/**
 * The client-safe half of the marketplace module.
 *
 * Split from `lib/api/marketplace.ts` for the same reason
 * `lib/search/kinds.ts` is split from `lib/api/search.ts`: that module
 * imports `apiFetch`, which is `server-only`, so a Client Component
 * importing *any value* from it — even a page-size constant — pulls
 * `next/headers` into the browser bundle and fails the build. Neither
 * `tsc` nor eslint catches it; only the bundler does.
 *
 * Types alone would be safe (they are erased), but keeping them here
 * with the constants means a component never has to know which of the
 * two modules a given export lives in, and a later `import type` →
 * `import` change cannot silently reintroduce the problem.
 */

export type Listing = components["schemas"]["ListingResponse"];
export type ListingPage = components["schemas"]["ListingPageResponse"];
export type Category = components["schemas"]["CategoryResponse"];
export type ListingVersion = components["schemas"]["ListingVersionResponse"];
export type Review = components["schemas"]["ReviewResponse"];
export type Install = components["schemas"]["InstallResponse"];
export type InstalledListing = components["schemas"]["InstalledListingResponse"];
export type CreateListingRequest = components["schemas"]["CreateListingRequest"];
export type UpdateListingRequest = components["schemas"]["UpdateListingRequest"];
export type PublishVersionRequest = components["schemas"]["PublishVersionRequest"];

/** Catalog page size. Twelve fills a three-column grid exactly. */
export const CATALOG_PAGE_SIZE = 12;

export interface CatalogFilters {
  q?: string | undefined;
  category?: string | undefined;
  /** `true` first-party only, `false` community only, omitted for both. */
  official?: boolean | undefined;
  free?: boolean | undefined;
  featured?: boolean | undefined;
  sort?: string | undefined;
  page?: number | undefined;
}
