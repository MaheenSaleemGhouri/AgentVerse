import { apiFetch } from "@/lib/api/client";
import {
  CATALOG_PAGE_SIZE,
  type CatalogFilters,
  type Category,
  type CreateListingRequest,
  type Install,
  type InstalledListing,
  type Listing,
  type ListingPage,
  type ListingVersion,
  type PublishVersionRequest,
  type Review,
  type UpdateListingRequest,
} from "@/lib/marketplace/types";

/**
 * The server half of the marketplace client.
 *
 * `apiFetch` is `server-only`, so nothing in a Client Component may
 * import this module. Types and constants live in
 * `lib/marketplace/types.ts`; these functions are reached from a Client
 * Component only through the Server Actions in `lib/api/actions.ts`.
 */

/**
 * The public catalog.
 *
 * Unauthenticated on the server — a marketplace has to be readable by
 * someone deciding whether to sign up. It is still fetched through
 * `apiFetch` here because the dashboard's catalog page is behind auth
 * anyway, and using one client keeps error handling uniform.
 */
export async function browseListings(filters: CatalogFilters = {}): Promise<ListingPage> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.category) params.set("category", filters.category);
  if (filters.official !== undefined) params.set("official", String(filters.official));
  if (filters.free) params.set("free", "true");
  if (filters.featured) params.set("featured", "true");
  if (filters.sort) params.set("sort", filters.sort);
  params.set("limit", String(CATALOG_PAGE_SIZE));
  params.set("offset", String(((filters.page ?? 1) - 1) * CATALOG_PAGE_SIZE));
  return apiFetch<ListingPage>(`/api/v1/marketplace/listings?${params.toString()}`);
}

export async function listCategories(): Promise<Category[]> {
  return apiFetch<Category[]>("/api/v1/marketplace/categories");
}

export async function listTemplates(category?: string): Promise<Listing[]> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  const query = params.toString();
  return apiFetch<Listing[]>(`/api/v1/marketplace/templates${query ? `?${query}` : ""}`);
}

export async function getListing(slug: string): Promise<Listing> {
  return apiFetch<Listing>(`/api/v1/marketplace/listings/${slug}`);
}

export async function listVersions(slug: string): Promise<ListingVersion[]> {
  return apiFetch<ListingVersion[]>(`/api/v1/marketplace/listings/${slug}/versions`);
}

export async function listReviews(slug: string): Promise<Review[]> {
  return apiFetch<Review[]>(`/api/v1/marketplace/listings/${slug}/reviews`);
}

// ── Workspace-scoped ────────────────────────────────────────────────

export async function listMyListings(workspaceId: string): Promise<Listing[]> {
  return apiFetch<Listing[]>(`/api/v1/workspaces/${workspaceId}/marketplace/listings`);
}

export async function listInstalls(workspaceId: string): Promise<InstalledListing[]> {
  return apiFetch<InstalledListing[]>(`/api/v1/workspaces/${workspaceId}/marketplace/installs`);
}

export async function installListing(
  workspaceId: string,
  slug: string,
  body: { version_number?: number | null; name?: string | null },
): Promise<Install> {
  return apiFetch<Install>(
    `/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}/install`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function submitReview(
  workspaceId: string,
  slug: string,
  body: { rating: number; body: string },
): Promise<Review> {
  // PUT, not POST: one review per workspace per listing, so submitting
  // again replaces rather than adds. The API enforces it with a unique
  // index; the verb makes the client's intent match.
  return apiFetch<Review>(
    `/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}/review`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export async function withdrawReview(workspaceId: string, slug: string): Promise<void> {
  await apiFetch<undefined>(
    `/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}/review`,
    { method: "DELETE" },
  );
}

export async function createListing(
  workspaceId: string,
  body: CreateListingRequest,
): Promise<Listing> {
  return apiFetch<Listing>(`/api/v1/workspaces/${workspaceId}/marketplace/listings`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateListing(
  workspaceId: string,
  slug: string,
  body: UpdateListingRequest,
): Promise<Listing> {
  return apiFetch<Listing>(`/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function publishListingVersion(
  workspaceId: string,
  slug: string,
  body: PublishVersionRequest,
): Promise<ListingVersion> {
  return apiFetch<ListingVersion>(
    `/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}/versions`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function submitListing(workspaceId: string, slug: string): Promise<Listing> {
  return apiFetch<Listing>(
    `/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}/submit`,
    { method: "POST" },
  );
}

export async function unlistListing(workspaceId: string, slug: string): Promise<Listing> {
  return apiFetch<Listing>(
    `/api/v1/workspaces/${workspaceId}/marketplace/listings/${slug}/unlist`,
    { method: "POST" },
  );
}
