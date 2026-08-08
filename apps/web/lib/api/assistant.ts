import { apiFetch } from "@/lib/api/client";
import type { AssistantMessage, AssistantSession } from "@/lib/assistant/types";

/**
 * The server half of the assistant client.
 *
 * Answering is deliberately absent: it streams, so it goes through the
 * BFF route at `app/api/assistant/[sessionId]/route.ts` instead. These
 * are the non-streaming reads and the session-open write.
 */

export async function listAssistantSessions(workspaceId: string): Promise<AssistantSession[]> {
  return apiFetch<AssistantSession[]>(`/api/v1/workspaces/${workspaceId}/assistant/sessions`);
}

export async function listAssistantMessages(
  workspaceId: string,
  sessionId: string
): Promise<AssistantMessage[]> {
  return apiFetch<AssistantMessage[]>(
    `/api/v1/workspaces/${workspaceId}/assistant/sessions/${sessionId}/messages`
  );
}

export async function openAssistantSession(
  workspaceId: string,
  question: string
): Promise<AssistantSession> {
  return apiFetch<AssistantSession>(`/api/v1/workspaces/${workspaceId}/assistant/sessions`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
