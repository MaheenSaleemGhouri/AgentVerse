import "server-only";

import { headers } from "next/headers";

import { auth } from "@/lib/auth";
import { env } from "@/lib/env";

/**
 * All server-side data access to apps/api goes through this module — no
 * Server Component calls `fetch` directly (CLAUDE.md §6).
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
  }
}

async function getBearerToken(): Promise<string> {
  const result = await auth.api.getToken({ headers: await headers() });
  if (!result?.token) {
    throw new ApiError(401, "No active session");
  }
  return result.token;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { skipJson?: boolean } = {}
): Promise<T> {
  const token = await getBearerToken();
  const response = await fetch(`${env.apiInternalUrl}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body || response.statusText);
  }

  if (response.status === 204 || init.skipJson) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
