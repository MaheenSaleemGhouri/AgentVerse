import { NextResponse } from "next/server";

import { getBearerToken } from "@/lib/api/client";
import { env } from "@/lib/env";

/**
 * Streams an audit-log export from apps/api to the browser.
 *
 * This exists because apps/api is internal-only and authenticated with a
 * server-side bearer token (CLAUDE.md §5) — the browser has nothing to
 * present and no route to it. Rather than fetching the export into a JS
 * blob and re-offering it, this handler authenticates, forwards, and
 * passes the upstream body through with its `Content-Disposition`
 * intact, so the file lands on disk as an ordinary download.
 *
 * Authorization is *not* re-implemented here: apps/api gates the export
 * on `require_admin`, so a non-admin's request fails upstream and this
 * handler forwards that status. Duplicating the role check here would
 * create a second place for it to drift.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ workspaceId: string }> }
): Promise<Response> {
  const { workspaceId } = await params;
  const requested = new URL(request.url).searchParams.get("format");
  // Allowlisted, never passed through: the upstream query string must
  // not be attacker-composable from this handler.
  const format = requested === "json" ? "json" : "csv";

  const upstream = new URL(
    `${env.apiInternalUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/audit-logs/export`
  );
  upstream.searchParams.set("format", format);
  for (const key of ["action", "actor_user_id"] as const) {
    const value = new URL(request.url).searchParams.get(key);
    if (value) upstream.searchParams.set(key, value);
  }

  let token: string;
  try {
    token = await getBearerToken();
  } catch {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(upstream, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!response.ok) {
    // Forward the upstream status rather than flattening it — a 403
    // from a non-admin must not read as a server error.
    return NextResponse.json(
      { error: "Export failed" },
      { status: response.status === 403 ? 403 : response.status }
    );
  }

  return new Response(response.body, {
    status: 200,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "text/csv",
      "Content-Disposition":
        response.headers.get("content-disposition") ??
        `attachment; filename="audit-logs.${format}"`,
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "no-store",
    },
  });
}
