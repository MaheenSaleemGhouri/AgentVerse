import { NextRequest } from "next/server";

import { getBearerToken } from "@/lib/api/client";
import { env } from "@/lib/env";

/**
 * BFF proxy for document upload, same rationale as the run-stream route:
 * the browser holds a session cookie, not the bearer token apps/api
 * requires, so the request has to pass through a same-origin handler
 * that can resolve one.
 *
 * A Server Action would be the shorter path, but it cannot report upload
 * progress — the client needs `XMLHttpRequest.upload.onprogress`, and
 * that requires a real endpoint to POST to. For a 25 MB PDF on a slow
 * connection, a spinner with no progress is the difference between
 * "working" and "frozen" (`ux-designer`: anything past a second shows
 * real incremental progress, never an indeterminate spinner).
 *
 * The body is streamed through untouched — this handler never buffers or
 * inspects the file. Admission (size cap, content sniffing) is apps/api's
 * job; duplicating it here would be a second source of truth that could
 * drift from the one that actually protects the worker.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ knowledgeBaseId: string }> }
): Promise<Response> {
  const { knowledgeBaseId } = await params;
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
    `${env.apiInternalUrl}/api/v1/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/documents`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        // The multipart boundary lives in the incoming Content-Type and
        // must be forwarded verbatim; regenerating it would invalidate
        // the body already in flight.
        "Content-Type": request.headers.get("content-type") ?? "multipart/form-data",
      },
      body: await request.arrayBuffer(),
      cache: "no-store",
    }
  );

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
