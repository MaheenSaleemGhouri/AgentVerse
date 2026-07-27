import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * AI teams — teams of *agents*, not workspace members.
 *
 * The product has two things called "team" and they share nothing:
 * `lib/api/workspaces.ts` owns human membership and RBAC roles, this
 * file owns multi-agent orchestration. Keeping them in separate modules
 * is what stops a future `Member` import from silently resolving to the
 * wrong one.
 *
 * Every type below is generated from the API's OpenAPI schema — never
 * hand-written, so a backend field rename fails the build here rather
 * than becoming `undefined` at runtime.
 */

export type Team = components["schemas"]["TeamResponse"];
export type TeamMember = components["schemas"]["TeamMemberResponse"];
export type TeamSession = components["schemas"]["TeamSessionResponse"];
export type TeamSessionPage = components["schemas"]["TeamSessionPage"];
export type ExecutionEvent = components["schemas"]["ExecutionEventResponse"];
export type Handoff = components["schemas"]["HandoffResponse"];
export type Communication = components["schemas"]["CommunicationResponse"];
export type TeamAnalytics = components["schemas"]["TeamAnalyticsResponse"];
export type CreateTeamRequest = components["schemas"]["CreateTeamRequest"];
export type UpdateTeamRequest = components["schemas"]["UpdateTeamRequest"];
export type AddMemberRequest = components["schemas"]["AddMemberRequest"];

export type Topology = Team["topology"];
export type TeamRole = TeamMember["role"];

/**
 * What a caller actually has to supply to create a team.
 *
 * The OpenAPI schema marks only `name` and `topology` as required — the
 * bounds all have server-side defaults. `openapi-typescript` runs with
 * `--default-non-nullable`, which promotes any defaulted field to
 * required in the generated type, so the generated `CreateTeamRequest`
 * demands four values the API is perfectly happy to fill in.
 *
 * Relaxed here rather than by changing the generator flag (which would
 * alter every other generated type) or by hardcoding the defaults in the
 * dialog (which would put a second copy of them in the frontend, where
 * they would drift from the API's — Rule 3).
 */
type DefaultedTeamFields =
  | "max_turns"
  | "max_cost_micro_usd"
  | "timeout_seconds"
  | "shared_memory_enabled";

export type CreateTeamInput = Omit<CreateTeamRequest, DefaultedTeamFields> &
  Partial<Pick<CreateTeamRequest, DefaultedTeamFields>>;

function base(workspaceId: string): string {
  return `/api/v1/workspaces/${workspaceId}/teams`;
}

export async function listTeams(workspaceId: string): Promise<Team[]> {
  return apiFetch<Team[]>(base(workspaceId));
}

export async function getTeam(workspaceId: string, teamId: string): Promise<Team> {
  return apiFetch<Team>(`${base(workspaceId)}/${teamId}`);
}

export async function createTeam(
  workspaceId: string,
  body: CreateTeamInput
): Promise<Team> {
  return apiFetch<Team>(base(workspaceId), { method: "POST", body: JSON.stringify(body) });
}

export async function updateTeam(
  workspaceId: string,
  teamId: string,
  body: UpdateTeamRequest
): Promise<Team> {
  return apiFetch<Team>(`${base(workspaceId)}/${teamId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function duplicateTeam(workspaceId: string, teamId: string): Promise<Team> {
  return apiFetch<Team>(`${base(workspaceId)}/${teamId}/duplicate`, { method: "POST" });
}

export async function deleteTeam(workspaceId: string, teamId: string): Promise<void> {
  await apiFetch<void>(`${base(workspaceId)}/${teamId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function addTeamMember(
  workspaceId: string,
  teamId: string,
  body: AddMemberRequest
): Promise<TeamMember> {
  return apiFetch<TeamMember>(`${base(workspaceId)}/${teamId}/members`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function removeTeamMember(
  workspaceId: string,
  teamId: string,
  memberId: string
): Promise<void> {
  await apiFetch<void>(`${base(workspaceId)}/${teamId}/members/${memberId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function reorderTeamMembers(
  workspaceId: string,
  teamId: string,
  memberIds: string[]
): Promise<Team> {
  return apiFetch<Team>(`${base(workspaceId)}/${teamId}/members/order`, {
    method: "PUT",
    body: JSON.stringify({ member_ids: memberIds }),
  });
}

export async function executeTeam(
  workspaceId: string,
  teamId: string,
  prompt: string
): Promise<TeamSession> {
  return apiFetch<TeamSession>(`${base(workspaceId)}/${teamId}/sessions`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
    // A team run is expensive; a double-submit from an impatient click
    // must not start (or bill for) a second one.
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
}

export async function listTeamSessions(
  workspaceId: string,
  teamId: string,
  options: { limit?: number; cursor?: string } = {}
): Promise<TeamSessionPage> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.cursor) params.set("cursor", options.cursor);
  const query = params.toString();
  return apiFetch<TeamSessionPage>(
    `${base(workspaceId)}/${teamId}/sessions${query ? `?${query}` : ""}`
  );
}

export async function getTeamSession(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<TeamSession> {
  return apiFetch<TeamSession>(`${base(workspaceId)}/${teamId}/sessions/${sessionId}`);
}

export async function listSessionEvents(
  workspaceId: string,
  teamId: string,
  sessionId: string,
  afterSequence = 0
): Promise<ExecutionEvent[]> {
  return apiFetch<ExecutionEvent[]>(
    `${base(workspaceId)}/${teamId}/sessions/${sessionId}/events?after_sequence=${afterSequence}`
  );
}

export async function listSessionHandoffs(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<Handoff[]> {
  return apiFetch<Handoff[]>(
    `${base(workspaceId)}/${teamId}/sessions/${sessionId}/handoffs`
  );
}

export async function listSessionCommunications(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<Communication[]> {
  return apiFetch<Communication[]>(
    `${base(workspaceId)}/${teamId}/sessions/${sessionId}/communications`
  );
}

export async function getTeamAnalytics(
  workspaceId: string,
  teamId: string
): Promise<TeamAnalytics> {
  return apiFetch<TeamAnalytics>(`${base(workspaceId)}/${teamId}/analytics`);
}
