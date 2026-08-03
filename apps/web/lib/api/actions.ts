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
  type OauthStart,
  type Permission,
  type PutCredentialRequest,
  putCredential as putCredentialApi,
  type RegisterCustomServerRequest,
  registerCustomServer as registerCustomServerApi,
  revokePermission as revokePermissionApi,
  startOauth as startOauthApi,
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
  type AuditLogFilters,
  type AuditLogPage,
  listAuditLogs as listAuditLogsApi,
} from "@/lib/api/audit-logs";
import {
  type OrganizationSettings,
  type UpdateOrganizationSettingsRequest,
  updateOrganizationSettings as updateOrganizationSettingsApi,
} from "@/lib/api/organization-settings";
import {
  type UpdateWorkspaceSettingsRequest,
  updateWorkspaceSettings as updateWorkspaceSettingsApi,
  type WorkspaceSettings,
} from "@/lib/api/workspace-settings";
import {
  deleteSsoConfiguration as deleteSsoConfigurationApi,
  listSsoConfigurations as listSsoConfigurationsApi,
  type SaveSsoConfigurationRequest,
  saveSsoConfiguration as saveSsoConfigurationApi,
  type SsoConfiguration,
} from "@/lib/api/sso";
import {
  type IssuedScimToken,
  issueScimToken as issueScimTokenApi,
  listScimTokens as listScimTokensApi,
  revokeScimToken as revokeScimTokenApi,
  type ScimToken,
} from "@/lib/api/scim-tokens";
import {
  type AddIpAllowlistEntryRequest,
  addIpAllowlistEntry as addIpAllowlistEntryApi,
  type IpAllowlistEntry,
  listIpAllowlist as listIpAllowlistApi,
  removeIpAllowlistEntry as removeIpAllowlistEntryApi,
} from "@/lib/api/ip-allowlist";
import {
  type CreateCustomRoleRequest,
  createCustomRole as createCustomRoleApi,
  type CustomRole,
  deleteCustomRole as deleteCustomRoleApi,
  listBuiltinRoles as listBuiltinRolesApi,
  listCustomRoles as listCustomRolesApi,
  type RoleDescriptor,
  type UpdateCustomRoleRequest,
  updateCustomRole as updateCustomRoleApi,
} from "@/lib/api/roles";
import {
  type GrantResourcePermissionRequest,
  grantResourcePermission as grantResourcePermissionApi,
  listResourcePermissions as listResourcePermissionsApi,
  type ResourcePermission,
  revokeResourcePermission as revokeResourcePermissionApi,
} from "@/lib/api/resource-permissions";
import {
  type ApiKey,
  createWorkspace as createWorkspaceApi,
  type IssueApiKeyRequest,
  issueApiKey as issueApiKeyApi,
  type InviteByEmailResponse,
  type IssuedApiKey,
  listApiKeys as listApiKeysApi,
  listMembers as listMembersApi,
  listMyWorkspaces as listMyWorkspacesApi,
  type Member,
  type Role,
  revokeApiKey as revokeApiKeyApi,
  rotateApiKey as rotateApiKeyApi,
  type Workspace,
} from "@/lib/api/workspaces";
import {
  attachWorkspace as attachWorkspaceApi,
  createOrganization as createOrganizationApi,
  deleteOrganization as deleteOrganizationApi,
  detachWorkspace as detachWorkspaceApi,
  listMyOrganizations as listMyOrganizationsApi,
  listOrgWorkspaces as listOrgWorkspacesApi,
  type Organization,
  type OrganizationWorkspace,
  renameOrganization as renameOrganizationApi,
} from "@/lib/api/organizations";
import {
  changeScopedMemberRole as changeScopedMemberRoleApi,
  inviteScopedMemberByEmail as inviteScopedMemberByEmailApi,
  listScopedMembers as listScopedMembersApi,
  type MemberScope,
  removeScopedMember as removeScopedMemberApi,
  type ScopedMember,
} from "@/lib/api/members";
import {
  acceptInvite as acceptInviteApi,
  type AcceptInviteResponse,
} from "@/lib/api/invitations";

export async function createWorkspaceAction(name: string): Promise<Workspace> {
  return createWorkspaceApi(name);
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
  body: IssueApiKeyRequest
): Promise<IssuedApiKey> {
  return issueApiKeyApi(workspaceId, body);
}

export async function revokeApiKeyAction(workspaceId: string, apiKeyId: string): Promise<void> {
  await revokeApiKeyApi(workspaceId, apiKeyId);
}

export async function rotateApiKeyAction(
  workspaceId: string,
  apiKeyId: string
): Promise<IssuedApiKey> {
  return rotateApiKeyApi(workspaceId, apiKeyId);
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

export async function startOauthAction(
  workspaceId: string,
  installedServerId: string
): Promise<OauthStart> {
  return startOauthApi(workspaceId, installedServerId);
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

export async function listAuditLogsAction(
  workspaceId: string,
  filters: AuditLogFilters = {}
): Promise<AuditLogPage> {
  return listAuditLogsApi(workspaceId, filters);
}

export async function updateWorkspaceSettingsAction(
  workspaceId: string,
  body: UpdateWorkspaceSettingsRequest
): Promise<WorkspaceSettings> {
  return updateWorkspaceSettingsApi(workspaceId, body);
}

export async function updateOrganizationSettingsAction(
  organizationId: string,
  body: UpdateOrganizationSettingsRequest
): Promise<OrganizationSettings> {
  return updateOrganizationSettingsApi(organizationId, body);
}

export async function listMyOrganizationsAction(): Promise<Organization[]> {
  return listMyOrganizationsApi();
}

export async function createOrganizationAction(name: string): Promise<Organization> {
  return createOrganizationApi(name);
}

export async function renameOrganizationAction(
  organizationId: string,
  name: string
): Promise<Organization> {
  return renameOrganizationApi(organizationId, name);
}

export async function deleteOrganizationAction(organizationId: string): Promise<void> {
  await deleteOrganizationApi(organizationId);
}

export async function listOrgWorkspacesAction(
  organizationId: string
): Promise<OrganizationWorkspace[]> {
  return listOrgWorkspacesApi(organizationId);
}

export async function attachWorkspaceAction(
  organizationId: string,
  workspaceId: string
): Promise<void> {
  await attachWorkspaceApi(organizationId, workspaceId);
}

export async function detachWorkspaceAction(
  organizationId: string,
  workspaceId: string
): Promise<void> {
  await detachWorkspaceApi(organizationId, workspaceId);
}

export async function listScopedMembersAction(scope: MemberScope): Promise<ScopedMember[]> {
  return listScopedMembersApi(scope);
}

export async function inviteScopedMemberByEmailAction(
  scope: MemberScope,
  email: string,
  role: Role
): Promise<InviteByEmailResponse> {
  return inviteScopedMemberByEmailApi(scope, email, role);
}

export async function changeScopedMemberRoleAction(
  scope: MemberScope,
  targetUserId: string,
  role: Role
): Promise<void> {
  await changeScopedMemberRoleApi(scope, targetUserId, role);
}

export async function removeScopedMemberAction(
  scope: MemberScope,
  targetUserId: string
): Promise<void> {
  await removeScopedMemberApi(scope, targetUserId);
}

export async function acceptInviteAction(token: string): Promise<AcceptInviteResponse> {
  return acceptInviteApi(token);
}

export async function listResourcePermissionsAction(
  workspaceId: string
): Promise<ResourcePermission[]> {
  return listResourcePermissionsApi(workspaceId);
}

export async function grantResourcePermissionAction(
  workspaceId: string,
  body: GrantResourcePermissionRequest
): Promise<ResourcePermission> {
  return grantResourcePermissionApi(workspaceId, body);
}

export async function revokeResourcePermissionAction(
  workspaceId: string,
  permissionId: string
): Promise<void> {
  await revokeResourcePermissionApi(workspaceId, permissionId);
}

export async function listIpAllowlistAction(
  workspaceId: string
): Promise<IpAllowlistEntry[]> {
  return listIpAllowlistApi(workspaceId);
}

export async function addIpAllowlistEntryAction(
  workspaceId: string,
  body: AddIpAllowlistEntryRequest
): Promise<IpAllowlistEntry> {
  return addIpAllowlistEntryApi(workspaceId, body);
}

export async function removeIpAllowlistEntryAction(
  workspaceId: string,
  entryId: string
): Promise<void> {
  await removeIpAllowlistEntryApi(workspaceId, entryId);
}

export async function listSsoConfigurationsAction(
  organizationId: string
): Promise<SsoConfiguration[]> {
  return listSsoConfigurationsApi(organizationId);
}

export async function saveSsoConfigurationAction(
  organizationId: string,
  body: SaveSsoConfigurationRequest
): Promise<SsoConfiguration> {
  return saveSsoConfigurationApi(organizationId, body);
}

export async function deleteSsoConfigurationAction(
  organizationId: string,
  configId: string
): Promise<void> {
  await deleteSsoConfigurationApi(organizationId, configId);
}

export async function listScimTokensAction(organizationId: string): Promise<ScimToken[]> {
  return listScimTokensApi(organizationId);
}

export async function issueScimTokenAction(
  organizationId: string,
  name: string
): Promise<IssuedScimToken> {
  return issueScimTokenApi(organizationId, name);
}

export async function revokeScimTokenAction(
  organizationId: string,
  tokenId: string
): Promise<void> {
  await revokeScimTokenApi(organizationId, tokenId);
}

export async function listBuiltinRolesAction(workspaceId: string): Promise<RoleDescriptor[]> {
  return listBuiltinRolesApi(workspaceId);
}

export async function listCustomRolesAction(workspaceId: string): Promise<CustomRole[]> {
  return listCustomRolesApi(workspaceId);
}

export async function createCustomRoleAction(
  workspaceId: string,
  body: CreateCustomRoleRequest
): Promise<CustomRole> {
  return createCustomRoleApi(workspaceId, body);
}

export async function updateCustomRoleAction(
  workspaceId: string,
  roleId: string,
  body: UpdateCustomRoleRequest
): Promise<CustomRole> {
  return updateCustomRoleApi(workspaceId, roleId, body);
}

export async function deleteCustomRoleAction(workspaceId: string, roleId: string): Promise<void> {
  return deleteCustomRoleApi(workspaceId, roleId);
}
