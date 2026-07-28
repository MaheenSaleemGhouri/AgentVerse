"use server";

/**
 * Server Actions wrapping lib/api/workspaces.ts's and lib/api/agents.ts's
 * mutations — the
 * server-only `apiFetch` (needs `next/headers` for the session) can't
 * be called directly from a Client Component (Next.js build correctly
 * rejects that); these thin `"use server"` wrappers are the supported
 * bridge. Read-only calls stay as plain functions invoked from Server
 * Components (create-workspace-form.tsx's parent, the [workspaceId]
 * page) — only client-triggered mutations need this file.
 */

import {
  type Agent,
  type AgentVersion,
  createAgent as createAgentApi,
  createAgentVersion as createAgentVersionApi,
  deleteAgent as deleteAgentApi,
  getAgent as getAgentApi,
  getLatestVersion as getLatestVersionApi,
  listAgents as listAgentsApi,
  publishAgent as publishAgentApi,
  type Run,
  runAgent as runAgentApi,
  type UpdateAgentVersionRequest,
} from "@/lib/api/agents";
import {
  createKnowledgeBase as createKnowledgeBaseApi,
  deleteDocument as deleteDocumentApi,
  deleteKnowledgeBase as deleteKnowledgeBaseApi,
  getKnowledgeBase as getKnowledgeBaseApi,
  type KbDocument,
  type KnowledgeBase,
  listDocuments as listDocumentsApi,
  listKnowledgeBases as listKnowledgeBasesApi,
  reindexDocument as reindexDocumentApi,
  type SearchResponse,
  searchKnowledgeBase as searchKnowledgeBaseApi,
} from "@/lib/api/knowledge";
import {
  type Credential,
  deleteCredential as deleteCredentialApi,
  getInstalled as getInstalledApi,
  getIntegrationMetrics as getIntegrationMetricsApi,
  type GrantPermissionRequest,
  grantPermission as grantPermissionApi,
  type InstalledServer,
  type InstallFromCatalogRequest,
  installFromCatalog as installFromCatalogApi,
  type IntegrationMetrics,
  listCatalog as listCatalogApi,
  listCredentials as listCredentialsApi,
  listInstalled as listInstalledApi,
  listPermissions as listPermissionsApi,
  listToolCalls as listToolCallsApi,
  type McpServer,
  type Permission,
  type PutCredentialRequest,
  putCredential as putCredentialApi,
  type RegisterCustomServerRequest,
  registerCustomServer as registerCustomServerApi,
  revokePermission as revokePermissionApi,
  type ToolCallPage,
  uninstall as uninstallApi,
  type UpdateInstalledServerRequest,
  updateInstalled as updateInstalledApi,
} from "@/lib/api/integrations";
import {
  type AddMemberRequest,
  addTeamMember as addTeamMemberApi,
  type Communication,
  createTeam as createTeamApi,
  type CreateTeamInput,
  deleteTeam as deleteTeamApi,
  duplicateTeam as duplicateTeamApi,
  type ExecutionEvent,
  executeTeam as executeTeamApi,
  getTeam as getTeamApi,
  getTeamAnalytics as getTeamAnalyticsApi,
  getTeamSession as getTeamSessionApi,
  type Handoff,
  listSessionCommunications as listSessionCommunicationsApi,
  listSessionEvents as listSessionEventsApi,
  listSessionHandoffs as listSessionHandoffsApi,
  listTeams as listTeamsApi,
  listTeamSessions as listTeamSessionsApi,
  removeTeamMember as removeTeamMemberApi,
  reorderTeamMembers as reorderTeamMembersApi,
  type Team,
  type TeamAnalytics,
  type TeamMember,
  type TeamSession,
  type TeamSessionPage,
  updateTeam as updateTeamApi,
  type UpdateTeamRequest,
} from "@/lib/api/teams";
import {
  type ApiKey,
  changeMemberRole as changeMemberRoleApi,
  createWorkspace as createWorkspaceApi,
  inviteMember as inviteMemberApi,
  issueApiKey as issueApiKeyApi,
  type IssuedApiKey,
  listApiKeys as listApiKeysApi,
  listMembers as listMembersApi,
  listMyWorkspaces as listMyWorkspacesApi,
  type Member,
  removeMember as removeMemberApi,
  revokeApiKey as revokeApiKeyApi,
  type Role,
  type Workspace,
} from "@/lib/api/workspaces";

export async function createWorkspaceAction(name: string): Promise<Workspace> {
  return createWorkspaceApi(name);
}

export async function inviteMemberAction(
  workspaceId: string,
  userId: string,
  role: Role
): Promise<void> {
  await inviteMemberApi(workspaceId, userId, role);
}

export async function changeMemberRoleAction(
  workspaceId: string,
  targetUserId: string,
  role: Role
): Promise<void> {
  await changeMemberRoleApi(workspaceId, targetUserId, role);
}

export async function removeMemberAction(workspaceId: string, targetUserId: string): Promise<void> {
  await removeMemberApi(workspaceId, targetUserId);
}

export async function createAgentAction(
  workspaceId: string,
  name: string,
  description: string | null
): Promise<{ agent: Agent; version: AgentVersion }> {
  return createAgentApi(workspaceId, {
    name,
    description,
    model: "gpt-4o-mini",
    system_instructions: "You are a helpful assistant.",
  });
}

export async function saveAgentVersionAction(
  workspaceId: string,
  agentId: string,
  body: UpdateAgentVersionRequest
): Promise<AgentVersion> {
  return createAgentVersionApi(workspaceId, agentId, body);
}

export async function publishAgentAction(workspaceId: string, agentId: string): Promise<Agent> {
  return publishAgentApi(workspaceId, agentId);
}

export async function deleteAgentAction(workspaceId: string, agentId: string): Promise<void> {
  await deleteAgentApi(workspaceId, agentId);
}

export async function runAgentAction(
  workspaceId: string,
  agentId: string,
  prompt: string,
  idempotencyKey: string
): Promise<Run> {
  return runAgentApi(workspaceId, agentId, prompt, idempotencyKey);
}

export async function createKnowledgeBaseAction(
  workspaceId: string,
  name: string,
  description: string | null
): Promise<KnowledgeBase> {
  return createKnowledgeBaseApi(workspaceId, { name, description });
}

export async function deleteKnowledgeBaseAction(
  workspaceId: string,
  knowledgeBaseId: string
): Promise<void> {
  await deleteKnowledgeBaseApi(workspaceId, knowledgeBaseId);
}

/**
 * Polled by the document list while anything is still ingesting.
 * Read-only, but a Server Action rather than a Server Component fetch
 * because the caller is a Client Component refreshing on an interval.
 */
export async function listDocumentsAction(
  workspaceId: string,
  knowledgeBaseId: string
): Promise<KbDocument[]> {
  return listDocumentsApi(workspaceId, knowledgeBaseId);
}

export async function listKnowledgeBasesAction(workspaceId: string): Promise<KnowledgeBase[]> {
  return listKnowledgeBasesApi(workspaceId);
}

export async function deleteDocumentAction(
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string
): Promise<void> {
  await deleteDocumentApi(workspaceId, knowledgeBaseId, documentId);
}

export async function reindexDocumentAction(
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string
): Promise<KbDocument> {
  return reindexDocumentApi(workspaceId, knowledgeBaseId, documentId);
}

export async function searchKnowledgeBaseAction(
  workspaceId: string,
  knowledgeBaseId: string,
  query: string
): Promise<SearchResponse> {
  return searchKnowledgeBaseApi(workspaceId, knowledgeBaseId, query);
}

/* -------------------------------------------------------------------------
 * Read actions
 *
 * Server Components fetch directly via `lib/api/*`; these exist for the
 * Client Components that drive TanStack Query hooks, which cannot import
 * the `server-only` client. Same functions, same auth path — this file
 * is a transport bridge, never a second data layer.
 * ---------------------------------------------------------------------- */

export async function listAgentsAction(workspaceId: string): Promise<Agent[]> {
  return listAgentsApi(workspaceId);
}

export async function getAgentAction(workspaceId: string, agentId: string): Promise<Agent> {
  return getAgentApi(workspaceId, agentId);
}

export async function getLatestVersionAction(
  workspaceId: string,
  agentId: string
): Promise<AgentVersion | null> {
  return getLatestVersionApi(workspaceId, agentId);
}

export async function getKnowledgeBaseAction(
  workspaceId: string,
  knowledgeBaseId: string
): Promise<KnowledgeBase> {
  return getKnowledgeBaseApi(workspaceId, knowledgeBaseId);
}

export async function listMembersAction(workspaceId: string): Promise<Member[]> {
  return listMembersApi(workspaceId);
}

export async function listApiKeysAction(workspaceId: string): Promise<ApiKey[]> {
  return listApiKeysApi(workspaceId);
}

export async function issueApiKeyAction(
  workspaceId: string,
  name: string
): Promise<IssuedApiKey> {
  return issueApiKeyApi(workspaceId, name);
}

export async function revokeApiKeyAction(workspaceId: string, apiKeyId: string): Promise<void> {
  await revokeApiKeyApi(workspaceId, apiKeyId);
}

export async function listMyWorkspacesAction(): Promise<Workspace[]> {
  return listMyWorkspacesApi();
}

// --- AI teams (multi-agent orchestration) --------------------------------
// Distinct from the workspace-member actions above: those manage humans
// and RBAC, these manage teams of agents. Same file because the Server
// Action bridge is a transport concern, not a domain boundary.

export async function listTeamsAction(workspaceId: string): Promise<Team[]> {
  return listTeamsApi(workspaceId);
}

export async function getTeamAction(workspaceId: string, teamId: string): Promise<Team> {
  return getTeamApi(workspaceId, teamId);
}

export async function createTeamAction(
  workspaceId: string,
  body: CreateTeamInput
): Promise<Team> {
  return createTeamApi(workspaceId, body);
}

export async function updateTeamAction(
  workspaceId: string,
  teamId: string,
  body: UpdateTeamRequest
): Promise<Team> {
  return updateTeamApi(workspaceId, teamId, body);
}

export async function duplicateTeamAction(workspaceId: string, teamId: string): Promise<Team> {
  return duplicateTeamApi(workspaceId, teamId);
}

export async function deleteTeamAction(workspaceId: string, teamId: string): Promise<void> {
  return deleteTeamApi(workspaceId, teamId);
}

export async function addTeamMemberAction(
  workspaceId: string,
  teamId: string,
  body: AddMemberRequest
): Promise<TeamMember> {
  return addTeamMemberApi(workspaceId, teamId, body);
}

export async function removeTeamMemberAction(
  workspaceId: string,
  teamId: string,
  memberId: string
): Promise<void> {
  return removeTeamMemberApi(workspaceId, teamId, memberId);
}

export async function reorderTeamMembersAction(
  workspaceId: string,
  teamId: string,
  memberIds: string[]
): Promise<Team> {
  return reorderTeamMembersApi(workspaceId, teamId, memberIds);
}

export async function executeTeamAction(
  workspaceId: string,
  teamId: string,
  prompt: string
): Promise<TeamSession> {
  return executeTeamApi(workspaceId, teamId, prompt);
}

export async function listTeamSessionsAction(
  workspaceId: string,
  teamId: string
): Promise<TeamSessionPage> {
  return listTeamSessionsApi(workspaceId, teamId);
}

export async function getTeamSessionAction(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<TeamSession> {
  return getTeamSessionApi(workspaceId, teamId, sessionId);
}

export async function listSessionEventsAction(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<ExecutionEvent[]> {
  return listSessionEventsApi(workspaceId, teamId, sessionId);
}

export async function listSessionHandoffsAction(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<Handoff[]> {
  return listSessionHandoffsApi(workspaceId, teamId, sessionId);
}

export async function listSessionCommunicationsAction(
  workspaceId: string,
  teamId: string,
  sessionId: string
): Promise<Communication[]> {
  return listSessionCommunicationsApi(workspaceId, teamId, sessionId);
}

export async function getTeamAnalyticsAction(
  workspaceId: string,
  teamId: string
): Promise<TeamAnalytics> {
  return getTeamAnalyticsApi(workspaceId, teamId);
}

// --- MCP integrations (Phase 6) ------------------------------------------
// Note the absence of a `getCredentialAction`: the API has no endpoint
// that returns a credential value, so there is nothing to wrap.

export async function listCatalogAction(
  workspaceId: string,
  options: { category?: string; q?: string } = {}
): Promise<McpServer[]> {
  return listCatalogApi(workspaceId, options);
}

export async function listInstalledAction(workspaceId: string): Promise<InstalledServer[]> {
  return listInstalledApi(workspaceId);
}

export async function getInstalledAction(
  workspaceId: string,
  installedServerId: string
): Promise<InstalledServer> {
  return getInstalledApi(workspaceId, installedServerId);
}

export async function installFromCatalogAction(
  workspaceId: string,
  body: InstallFromCatalogRequest
): Promise<InstalledServer> {
  return installFromCatalogApi(workspaceId, body);
}

export async function registerCustomServerAction(
  workspaceId: string,
  body: RegisterCustomServerRequest
): Promise<InstalledServer> {
  return registerCustomServerApi(workspaceId, body);
}

export async function updateInstalledAction(
  workspaceId: string,
  installedServerId: string,
  body: UpdateInstalledServerRequest
): Promise<InstalledServer> {
  return updateInstalledApi(workspaceId, installedServerId, body);
}

export async function uninstallAction(
  workspaceId: string,
  installedServerId: string
): Promise<void> {
  return uninstallApi(workspaceId, installedServerId);
}

export async function putCredentialAction(
  workspaceId: string,
  installedServerId: string,
  body: PutCredentialRequest
): Promise<Credential> {
  return putCredentialApi(workspaceId, installedServerId, body);
}

export async function listCredentialsAction(
  workspaceId: string,
  installedServerId: string
): Promise<Credential[]> {
  return listCredentialsApi(workspaceId, installedServerId);
}

export async function deleteCredentialAction(
  workspaceId: string,
  installedServerId: string,
  key: string
): Promise<void> {
  return deleteCredentialApi(workspaceId, installedServerId, key);
}

export async function grantPermissionAction(
  workspaceId: string,
  installedServerId: string,
  body: GrantPermissionRequest
): Promise<Permission> {
  return grantPermissionApi(workspaceId, installedServerId, body);
}

export async function listPermissionsAction(
  workspaceId: string,
  installedServerId: string,
  agentId?: string
): Promise<Permission[]> {
  return listPermissionsApi(workspaceId, installedServerId, agentId);
}

export async function revokePermissionAction(
  workspaceId: string,
  installedServerId: string,
  permissionId: string
): Promise<void> {
  return revokePermissionApi(workspaceId, installedServerId, permissionId);
}

export async function listToolCallsAction(
  workspaceId: string,
  // `| undefined` spelled out to match the client's signature under
  // `exactOptionalPropertyTypes` — callers spread optional filter values.
  options: {
    installedServerId?: string | undefined;
    runId?: string | undefined;
    status?: string | undefined;
    limit?: number | undefined;
    cursor?: string | undefined;
  } = {}
): Promise<ToolCallPage> {
  return listToolCallsApi(workspaceId, options);
}

export async function getIntegrationMetricsAction(
  workspaceId: string,
  installedServerId?: string
): Promise<IntegrationMetrics> {
  return getIntegrationMetricsApi(workspaceId, installedServerId);
}
