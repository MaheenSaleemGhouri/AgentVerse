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
  type BillingInterval,
  cancelSubscription as cancelSubscriptionApi,
  changePlan as changePlanApi,
  type CreditBalance,
  createCheckoutSession as createCheckoutSessionApi,
  createPortalSession as createPortalSessionApi,
  type DraftInvoice,
  type Entitlements,
  getCredits as getCreditsApi,
  getEntitlements as getEntitlementsApi,
  getInvoicePreview as getInvoicePreviewApi,
  getReferrals as getReferralsApi,
  getSubscription as getSubscriptionApi,
  getUsage as getUsageApi,
  type Invoice,
  listInvoices as listInvoicesApi,
  listPaymentMethods as listPaymentMethodsApi,
  type PaymentMethod,
  type PeriodUsage,
  type PlanChangeQuote,
  type PlanTier,
  quotePlanChange as quotePlanChangeApi,
  redeemCoupon as redeemCouponApi,
  type ReferralSummary,
  resumeSubscription as resumeSubscriptionApi,
  type Subscription,
} from "@/lib/api/billing";
import { ApiError } from "@/lib/api/client";
import {
  listNotifications as listNotificationsApi,
  markAllNotificationsRead as markAllNotificationsReadApi,
  markNotificationRead as markNotificationReadApi,
  type NotificationList,
} from "@/lib/api/notifications";
import {
  approveListing as approveListingApi,
  featureListing as featureListingApi,
  listModerationQueue as listModerationQueueApi,
  rejectListing as rejectListingApi,
} from "@/lib/api/admin";
import type { ModerationListing } from "@/lib/admin/types";
import {
  listAssistantMessages as listAssistantMessagesApi,
  listAssistantSessions as listAssistantSessionsApi,
  openAssistantSession as openAssistantSessionApi,
} from "@/lib/api/assistant";
import type { AssistantMessage, AssistantSession } from "@/lib/assistant/types";
import {
  browseListings as browseListingsApi,
  createListing as createListingApi,
  installListing as installListingApi,
  listMyListings as listMyListingsApi,
  listReviews as listReviewsApi,
  publishListingVersion as publishListingVersionApi,
  shareListing as shareListingApi,
  startMarketplaceCheckout as startMarketplaceCheckoutApi,
  submitListing as submitListingApi,
  submitReview as submitReviewApi,
  unlistListing as unlistListingApi,
  updateListing as updateListingApi,
  withdrawReview as withdrawReviewApi,
} from "@/lib/api/marketplace";
import type {
  CatalogFilters,
  CreateListingRequest,
  Install,
  Listing,
  ListingPage,
  ListingVersion,
  MarketplaceCheckout,
  PublishVersionRequest,
  Review,
  UpdateListingRequest,
} from "@/lib/marketplace/types";
import { searchWorkspace as searchWorkspaceApi } from "@/lib/api/search";
import type { SearchKind, SearchResults } from "@/lib/search/kinds";
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
  type CollabTicketResponse,
  type CreateWorkflowRequest,
  createWorkflow as createWorkflowApi,
  type CreateWorkflowVersionRequest,
  createWorkflowVersion as createWorkflowVersionApi,
  diffWorkflowVersions as diffWorkflowVersionsApi,
  getLatestWorkflowVersion as getLatestWorkflowVersionApi,
  getWorkflow as getWorkflowApi,
  getWorkflowRun as getWorkflowRunApi,
  getWorkflowVersion as getWorkflowVersionApi,
  listWorkflowRunNodes as listWorkflowRunNodesApi,
  listWorkflows as listWorkflowsApi,
  mintCollabTicket as mintCollabTicketApi,
  publishWorkflow as publishWorkflowApi,
  resolveWorkflowApproval as resolveWorkflowApprovalApi,
  submitWorkflowRun as submitWorkflowRunApi,
  type Workflow,
  type WorkflowNodeRun,
  type WorkflowRun,
  type WorkflowVersion,
  type WorkflowVersionDiff,
} from "@/lib/api/workflows";
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
  listMyDevices as listMyDevicesApi,
  type PasswordPolicy,
  revokeDevice as revokeDeviceApi,
  setPasswordPolicy as setPasswordPolicyApi,
  type TrustedDevice,
  type UpdatePasswordPolicyRequest,
} from "@/lib/api/security";
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
  type IssuedMcpClient,
  type IssueMcpClientRequest,
  issueMcpClient as issueMcpClientApi,
  listApiKeys as listApiKeysApi,
  listMcpClients as listMcpClientsApi,
  listMembers as listMembersApi,
  listMyWorkspaces as listMyWorkspacesApi,
  type McpClient,
  type Member,
  type Role,
  revokeApiKey as revokeApiKeyApi,
  revokeMcpClient as revokeMcpClientApi,
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
import {
  createSupportTicket as createSupportTicketApi,
  resolveSupportTicket as resolveSupportTicketApi,
  type SupportTicket,
} from "@/lib/api/support-tickets";

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

export async function listMcpClientsAction(workspaceId: string): Promise<McpClient[]> {
  return listMcpClientsApi(workspaceId);
}

export async function issueMcpClientAction(
  workspaceId: string,
  body: IssueMcpClientRequest
): Promise<IssuedMcpClient> {
  return issueMcpClientApi(workspaceId, body);
}

export async function revokeMcpClientAction(
  workspaceId: string,
  mcpClientId: string
): Promise<void> {
  await revokeMcpClientApi(workspaceId, mcpClientId);
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

export async function listMyDevicesAction(): Promise<TrustedDevice[]> {
  return listMyDevicesApi();
}

export async function revokeDeviceAction(deviceId: string): Promise<void> {
  return revokeDeviceApi(deviceId);
}

export async function setPasswordPolicyAction(
  organizationId: string,
  body: UpdatePasswordPolicyRequest
): Promise<PasswordPolicy> {
  return setPasswordPolicyApi(organizationId, body);
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

// --- Billing (Phase 9) -------------------------------------------------
// Client components read billing data through TanStack Query, which
// cannot call the server-only `apiFetch` directly; these are the
// supported bridge. The pricing page's catalog read is deliberately
// absent — it is unauthenticated and server-rendered, so it calls
// `listPublicPlans` from a Server Component with no action in between.

export async function getSubscriptionAction(workspaceId: string): Promise<Subscription | null> {
  try {
    return await getSubscriptionApi(workspaceId);
  } catch (error) {
    // 404 is the documented answer for a workspace that has never
    // subscribed — a Free workspace operating exactly as intended, not a
    // failure. Mapped to `null` here so every caller does not repeat the
    // status check.
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function getEntitlementsAction(workspaceId: string): Promise<Entitlements> {
  return getEntitlementsApi(workspaceId);
}

export async function getUsageAction(workspaceId: string): Promise<PeriodUsage> {
  return getUsageApi(workspaceId);
}

export async function getInvoicePreviewAction(workspaceId: string): Promise<DraftInvoice> {
  return getInvoicePreviewApi(workspaceId);
}

export async function getCreditsAction(workspaceId: string): Promise<CreditBalance> {
  return getCreditsApi(workspaceId);
}

export async function getReferralsAction(workspaceId: string): Promise<ReferralSummary> {
  return getReferralsApi(workspaceId);
}

/**
 * Invoices and payment methods live at the payment provider, so both
 * return 503 in an environment with no provider configured — local
 * development, CI, and preview environments legitimately run that way.
 * Surfaced as `null` rather than thrown, so the panel can say "payments
 * are not configured here" instead of rendering a generic error for a
 * deliberate state.
 */
export async function listInvoicesAction(workspaceId: string): Promise<Invoice[] | null> {
  try {
    return await listInvoicesApi(workspaceId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      return null;
    }
    throw error;
  }
}

export async function listPaymentMethodsAction(
  workspaceId: string
): Promise<PaymentMethod[] | null> {
  try {
    return await listPaymentMethodsApi(workspaceId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      return null;
    }
    throw error;
  }
}

export async function createCheckoutSessionAction(
  workspaceId: string,
  body: { plan_slug: PlanTier; interval: BillingInterval; coupon_code?: string | null }
): Promise<{ checkout_url: string; session_id: string }> {
  return createCheckoutSessionApi(workspaceId, body);
}

export async function createPortalSessionAction(
  workspaceId: string
): Promise<{ portal_url: string }> {
  return createPortalSessionApi(workspaceId);
}

export async function quotePlanChangeAction(
  workspaceId: string,
  body: { plan_slug: PlanTier; interval: BillingInterval }
): Promise<PlanChangeQuote> {
  return quotePlanChangeApi(workspaceId, body);
}

export async function changePlanAction(
  workspaceId: string,
  body: { plan_slug: PlanTier; interval: BillingInterval },
  idempotencyKey: string
): Promise<Subscription> {
  return changePlanApi(workspaceId, body, idempotencyKey);
}

export async function cancelSubscriptionAction(
  workspaceId: string,
  body: { at_period_end: boolean; reason?: string | null }
): Promise<Subscription> {
  return cancelSubscriptionApi(workspaceId, body);
}

export async function resumeSubscriptionAction(workspaceId: string): Promise<Subscription> {
  return resumeSubscriptionApi(workspaceId);
}

export async function redeemCouponAction(
  workspaceId: string,
  code: string
): Promise<{ code: string; credited_cents: number; balance_cents: number }> {
  return redeemCouponApi(workspaceId, code);
}

// --- Notifications (Phase 9) -------------------------------------------

export async function listNotificationsAction(
  workspaceId: string,
  options: { unreadOnly?: boolean; limit?: number } = {}
): Promise<NotificationList> {
  return listNotificationsApi(workspaceId, options);
}

export async function markNotificationReadAction(
  workspaceId: string,
  notificationId: string
): Promise<void> {
  return markNotificationReadApi(workspaceId, notificationId);
}

export async function markAllNotificationsReadAction(
  workspaceId: string
): Promise<{ marked: number }> {
  return markAllNotificationsReadApi(workspaceId);
}

/**
 * Read-only, unlike everything else in this file — and it has to be.
 *
 * The command palette is a Client Component, so it cannot call the
 * server-only `apiFetch` (which needs `next/headers` for the session)
 * directly. Every other read in the app is issued from a Server
 * Component that already has the request context; a palette that opens
 * on ⌘K and queries as the user types has no such moment.
 */
export async function searchWorkspaceAction(
  workspaceId: string,
  query: string,
  kinds?: readonly SearchKind[]
): Promise<SearchResults> {
  return searchWorkspaceApi(workspaceId, query, kinds);
}

// ── Marketplace ─────────────────────────────────────────────────────

export async function browseListingsAction(filters: CatalogFilters): Promise<ListingPage> {
  return browseListingsApi(filters);
}

export async function listReviewsAction(slug: string): Promise<Review[]> {
  return listReviewsApi(slug);
}

export async function listMyListingsAction(workspaceId: string): Promise<Listing[]> {
  return listMyListingsApi(workspaceId);
}

export async function installListingAction(
  workspaceId: string,
  slug: string,
  body: { version_number?: number | null; name?: string | null }
): Promise<Install> {
  return installListingApi(workspaceId, slug, body);
}

export async function startMarketplaceCheckoutAction(
  workspaceId: string,
  slug: string
): Promise<MarketplaceCheckout> {
  return startMarketplaceCheckoutApi(workspaceId, slug);
}

export async function shareListingAction(workspaceId: string, slug: string): Promise<void> {
  await shareListingApi(workspaceId, slug);
}

export async function submitReviewAction(
  workspaceId: string,
  slug: string,
  body: { rating: number; body: string }
): Promise<Review> {
  return submitReviewApi(workspaceId, slug, body);
}

export async function withdrawReviewAction(workspaceId: string, slug: string): Promise<void> {
  return withdrawReviewApi(workspaceId, slug);
}

export async function createListingAction(
  workspaceId: string,
  body: CreateListingRequest
): Promise<Listing> {
  return createListingApi(workspaceId, body);
}

export async function updateListingAction(
  workspaceId: string,
  slug: string,
  body: UpdateListingRequest
): Promise<Listing> {
  return updateListingApi(workspaceId, slug, body);
}

export async function publishListingVersionAction(
  workspaceId: string,
  slug: string,
  body: PublishVersionRequest
): Promise<ListingVersion> {
  return publishListingVersionApi(workspaceId, slug, body);
}

export async function submitListingAction(workspaceId: string, slug: string): Promise<Listing> {
  return submitListingApi(workspaceId, slug);
}

export async function unlistListingAction(workspaceId: string, slug: string): Promise<Listing> {
  return unlistListingApi(workspaceId, slug);
}

// ---- assistant ---------------------------------------------------------
// Answering is not here: it streams, and a Server Action cannot return a
// stream. That path goes through the BFF route at
// `app/api/assistant/[sessionId]/route.ts`.

export async function listAssistantSessionsAction(
  workspaceId: string
): Promise<AssistantSession[]> {
  return listAssistantSessionsApi(workspaceId);
}

export async function listAssistantMessagesAction(
  workspaceId: string,
  sessionId: string
): Promise<AssistantMessage[]> {
  return listAssistantMessagesApi(workspaceId, sessionId);
}

export async function openAssistantSessionAction(
  workspaceId: string,
  question: string
): Promise<AssistantSession> {
  return openAssistantSessionApi(workspaceId, question);
}

// ---- platform admin ----------------------------------------------------
// Global, not workspace-scoped: moderating a listing is a judgement
// about another workspace's listing, which no workspace role expresses.
// Authority is `platform_admins`, checked server-side on every call —
// these wrappers add no gate of their own and must not be read as one.

export async function listModerationQueueAction(): Promise<ModerationListing[]> {
  return listModerationQueueApi();
}

export async function approveListingAction(
  listingId: string,
  note: string
): Promise<ModerationListing> {
  return approveListingApi(listingId, note);
}

export async function rejectListingAction(
  listingId: string,
  note: string
): Promise<ModerationListing> {
  return rejectListingApi(listingId, note);
}

export async function featureListingAction(
  listingId: string,
  isFeatured: boolean
): Promise<ModerationListing> {
  return featureListingApi(listingId, isFeatured);
}

export async function createSupportTicketAction(
  workspaceId: string,
  body: { agent_id: string; subject: string; body: string }
): Promise<SupportTicket> {
  return createSupportTicketApi(workspaceId, body);
}

export async function resolveSupportTicketAction(
  workspaceId: string,
  ticketId: string
): Promise<SupportTicket> {
  return resolveSupportTicketApi(workspaceId, ticketId);
}

// ---- workflows (Phase 10, docs/adr/0016) -------------------------------

export async function listWorkflowsAction(workspaceId: string): Promise<Workflow[]> {
  return listWorkflowsApi(workspaceId);
}

export async function getWorkflowAction(
  workspaceId: string,
  workflowId: string
): Promise<Workflow> {
  return getWorkflowApi(workspaceId, workflowId);
}

export async function createWorkflowAction(
  workspaceId: string,
  body: CreateWorkflowRequest
): Promise<{ workflow: Workflow; version: WorkflowVersion }> {
  return createWorkflowApi(workspaceId, body);
}

export async function getLatestWorkflowVersionAction(
  workspaceId: string,
  workflowId: string
): Promise<WorkflowVersion | null> {
  return getLatestWorkflowVersionApi(workspaceId, workflowId);
}

export async function getWorkflowVersionAction(
  workspaceId: string,
  workflowId: string,
  versionId: string
): Promise<WorkflowVersion> {
  return getWorkflowVersionApi(workspaceId, workflowId, versionId);
}

export async function createWorkflowVersionAction(
  workspaceId: string,
  workflowId: string,
  body: CreateWorkflowVersionRequest
): Promise<WorkflowVersion> {
  return createWorkflowVersionApi(workspaceId, workflowId, body);
}

export async function diffWorkflowVersionsAction(
  workspaceId: string,
  workflowId: string,
  versionId: string,
  against: string
): Promise<WorkflowVersionDiff> {
  return diffWorkflowVersionsApi(workspaceId, workflowId, versionId, against);
}

export async function publishWorkflowAction(
  workspaceId: string,
  workflowId: string,
  versionId: string
): Promise<Workflow> {
  return publishWorkflowApi(workspaceId, workflowId, versionId);
}

export async function submitWorkflowRunAction(
  workspaceId: string,
  workflowId: string,
  input: Record<string, unknown>,
  idempotencyKey: string
): Promise<WorkflowRun> {
  return submitWorkflowRunApi(workspaceId, workflowId, input, idempotencyKey);
}

export async function getWorkflowRunAction(
  workspaceId: string,
  workflowId: string,
  runId: string
): Promise<WorkflowRun> {
  return getWorkflowRunApi(workspaceId, workflowId, runId);
}

export async function listWorkflowRunNodesAction(
  workspaceId: string,
  workflowId: string,
  runId: string
): Promise<WorkflowNodeRun[]> {
  return listWorkflowRunNodesApi(workspaceId, workflowId, runId);
}

export async function resolveWorkflowApprovalAction(
  workspaceId: string,
  workflowId: string,
  runId: string,
  nodeId: string,
  decision: "approved" | "rejected",
  comment: string | null
): Promise<WorkflowNodeRun> {
  return resolveWorkflowApprovalApi(workspaceId, workflowId, runId, nodeId, decision, comment);
}

export async function mintCollabTicketAction(
  workspaceId: string,
  workflowId: string
): Promise<CollabTicketResponse> {
  return mintCollabTicketApi(workspaceId, workflowId);
}
