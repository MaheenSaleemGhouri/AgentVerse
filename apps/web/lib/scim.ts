import "server-only";

import { env } from "@/lib/env";

/**
 * The base URL an identity provider points its SCIM connector at.
 *
 * SCIM is served by apps/api (not this app), so this is derived from the
 * API's *public* origin. Returns `null` when `API_PUBLIC_URL` is unset:
 * showing `API_INTERNAL_URL` instead would give an administrator a URL
 * that resolves inside the cluster and nowhere else — a value that looks
 * right and fails at the one moment it matters.
 */
export function scimBaseUrl(): string | null {
  if (!env.apiPublicUrl) return null;
  return `${env.apiPublicUrl.replace(/\/$/, "")}/scim/v2`;
}
