import { apiFetch } from "@/lib/api/client";
import type { ModerationListing } from "@/lib/admin/types";

/**
 * The platform-staff surface.
 *
 * Every route here is global, not workspace-scoped — moderating a
 * listing is a judgement about a listing owned by *another* workspace,
 * which no workspace role can express. Authority comes from
 * `platform_admins` via `require_platform_admin`, and the moderation
 * routes answer 404 rather than 403 so the surface does not confirm its
 * own existence to a caller with no business there.
 */

export async function isPlatformAdmin(): Promise<boolean> {
  const { is_platform_admin } = await apiFetch<{ is_platform_admin: boolean }>(
    "/api/v1/admin/session"
  );
  return is_platform_admin;
}

export async function listModerationQueue(): Promise<ModerationListing[]> {
  return apiFetch<ModerationListing[]>("/api/v1/admin/marketplace/queue");
}

export async function approveListing(
  listingId: string,
  note: string
): Promise<ModerationListing> {
  return apiFetch<ModerationListing>(
    `/api/v1/admin/marketplace/listings/${listingId}/approve`,
    { method: "POST", body: JSON.stringify({ note }) }
  );
}

export async function rejectListing(
  listingId: string,
  note: string
): Promise<ModerationListing> {
  return apiFetch<ModerationListing>(
    `/api/v1/admin/marketplace/listings/${listingId}/reject`,
    { method: "POST", body: JSON.stringify({ note }) }
  );
}

export async function featureListing(
  listingId: string,
  isFeatured: boolean
): Promise<ModerationListing> {
  return apiFetch<ModerationListing>(
    `/api/v1/admin/marketplace/listings/${listingId}/feature`,
    { method: "POST", body: JSON.stringify({ is_featured: isFeatured }) }
  );
}
