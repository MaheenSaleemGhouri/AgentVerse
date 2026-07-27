import { NextRequest } from "next/server";

import { getBearerToken } from "@/lib/api/client";
import { env } from "@/lib/env";

/**
 * BFF proxy for the multi-agent runtime SSE stream.
 *
 * Same reason as the single-agent proxy at `app/api/runs/[runId]/stream`:
 * native `EventSource` cannot set an `Authorization` header, and the
 * FastAPI route requires one — so this same-origin route holds the
 * browser's session cookie, resolves it to a bearer token server-side,
 * and pipes the upstream body through unmodified.
 *
 * A separate route rather than a parameterised one because the upstream
 * paths differ in shape (an agent run is nested under an agent, a team
 * session under a team), and collapsing them would mean a handler that
 * branches on which kind of run it was asked for.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
): Promise<Response> {
  const { sessionId } = await params;
  const workspaceId = request.nextUrl.searchParams.get("workspaceId");
  const teamId = request.nextUrl.searchParams.get("teamId");

  if (!workspaceId || !teamId) {
    return new Response("Missing workspaceId or teamId", { status: 400 });
  }

  let token: string;
  try {
    token = await getBearerToken();
  } catch {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${env.apiInternalUrl}/api/v1/workspaces/${workspaceId}/teams/${teamId}/sessions/${sessionId}/stream`,
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
