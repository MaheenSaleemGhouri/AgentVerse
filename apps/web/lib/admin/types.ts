/**
 * Client-safe platform-admin types.
 *
 * Split from `lib/api/admin.ts` for the usual reason — that module is
 * `server-only` and a Client Component importing a value from it fails
 * the production build.
 */

import type { Listing } from "@/lib/marketplace/types";

export type ModerationListing = Listing;

/** Why a rejection needs a note and an approval does not: a publisher
 * told "rejected" with no reason cannot fix anything, and will submit
 * the same listing again. Enforced server-side too (422). */
export const MIN_REJECTION_NOTE_LENGTH = 1;
