import { NextRequest } from "next/server";

import { getBearerToken } from "@/lib/api/client";
import { env } from "@/lib/env";

/**
 * BFF proxy for the assistant's SSE answer stream.
 *
 * A POST rather than a GET, which is why this exists separately from
 * the run-stream proxy: the question is a body, so `EventSource` is out
 * entirely and the client reads the response stream itself. Same
 * reasoning otherwise — this same-origin route holds the session cookie,
 * resolves it to a bearer token server-side, and pipes the upstream body
 * through unmodified.
 *
 * The question is forwarded, not inspected. Validation belongs to the
 * API's Pydantic schema, which is the trust boundary; re-checking length
 * here would be a second copy of a rule that can drift from the one that
 * actually enforces it.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
): Promise<Response> {
  const { sessionId } = await params;
  const workspaceId = request.nextUrl.searchParams.get("workspaceId");

  if (!workspaceId) {
    return new Response("Missing workspaceId", { status: 400 });
  }

  let token: string;
  try {
    token = await getBearerToken();
  } catch {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${env.apiInternalUrl}/api/v1/workspaces/${workspaceId}/assistant/sessions/${sessionId}/messages`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    }
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
