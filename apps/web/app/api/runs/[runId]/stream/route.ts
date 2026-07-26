import { NextRequest } from "next/server";

import { getBearerToken } from "@/lib/api/client";
import { env } from "@/lib/env";

/**
 * BFF proxy for the SSE run-stream (nextjs-expert: route handlers exist
 * for exactly this — auth-cookie handling a client can't do itself).
 * Native `EventSource` can't set an `Authorization` header, and the
 * FastAPI route requires one; this same-origin route holds the
 * browser's session cookie, resolves it to a bearer token server-side,
 * and pipes the upstream SSE body straight through unmodified.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
): Promise<Response> {
  const { runId } = await params;
  const workspaceId = request.nextUrl.searchParams.get("workspaceId");
  const agentId = request.nextUrl.searchParams.get("agentId");

  if (!workspaceId || !agentId) {
    return new Response("Missing workspaceId or agentId", { status: 400 });
  }

  let token: string;
  try {
    token = await getBearerToken();
  } catch {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${env.apiInternalUrl}/api/v1/workspaces/${workspaceId}/agents/${agentId}/runs/${runId}/stream`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }
  );

  if (!upstream.ok || upstream.body === null) {
    return new Response("Upstream stream unavailable", { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
