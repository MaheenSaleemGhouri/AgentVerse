import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type AcceptInviteResponse = components["schemas"]["AcceptInviteResponse"];

/** Target-agnostic: the token itself carries and authorizes the target
 * workspace or organization — the caller need not be a member of either
 * yet (that is the entire point of an invitation). */
export async function acceptInvite(token: string): Promise<AcceptInviteResponse> {
  return apiFetch<AcceptInviteResponse>("/api/v1/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}
