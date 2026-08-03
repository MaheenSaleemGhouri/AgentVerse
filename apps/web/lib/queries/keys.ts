/**
 * The single query-key factory.
 *
 * Keys are built here rather than inline at each `useQuery` call so that
 * an invalidation after a mutation cannot miss a cache entry because two
 * call sites spelled the same key differently. Every key is scoped by
 * `workspaceId` first, mirroring the API's own tenancy scoping — so
 * switching workspace can never serve another tenant's cached rows.
 */
export const queryKeys = {
  workspaces: () => ["workspaces"] as const,

  organizations: () => ["organizations"] as const,

  organizationWorkspaces: (organizationId: string) =>
    ["organizations", organizationId, "workspaces"] as const,
  organizationSettings: (organizationId: string) =>
    ["organizations", organizationId, "settings"] as const,
  passwordPolicy: (organizationId: string) =>
    ["organizations", organizationId, "password-policy"] as const,
  // Not workspace-scoped: trusted devices belong to the signed-in
  // identity, not to whichever workspace happens to be open.
  myDevices: () => ["me", "devices"] as const,
  mySecurityEvents: () => ["me", "security-events"] as const,
  workspaceSecurityEvents: (workspaceId: string) =>
    ["workspaces", workspaceId, "security-events"] as const,
  securityScore: (workspaceId: string) => ["workspaces", workspaceId, "security-score"] as const,

  // Shared by workspace- and organization-scoped member lists (`lib/api/members.ts`)
  // — scoped by `scope.type` first so switching scope can never serve the
  // other scope's cached rows, mirroring the workspace-first convention above.
  scopedMembers: (scope: { type: "workspace" | "organization"; id: string }) =>
    [scope.type, scope.id, "members"] as const,

  apiKeys: (workspaceId: string) => ["workspaces", workspaceId, "api-keys"] as const,

  auditLogs: (workspaceId: string, filters: Record<string, string | undefined> = {}) =>
    ["workspaces", workspaceId, "audit-logs", filters] as const,

  workspaceSettings: (workspaceId: string) => ["workspaces", workspaceId, "settings"] as const,

  ssoConfigurations: (organizationId: string) =>
    ["organizations", organizationId, "sso"] as const,

  ipAllowlist: (workspaceId: string) =>
    ["workspaces", workspaceId, "ip-allowlist"] as const,

  resourcePermissions: (workspaceId: string) =>
    ["workspaces", workspaceId, "resource-permissions"] as const,

  builtinRoles: (workspaceId: string) =>
    ["workspaces", workspaceId, "roles", "builtin"] as const,

  customRoles: (workspaceId: string) => ["workspaces", workspaceId, "roles"] as const,

  agents: {
    all: (workspaceId: string) => ["workspaces", workspaceId, "agents"] as const,
    detail: (workspaceId: string, agentId: string) =>
      ["workspaces", workspaceId, "agents", agentId] as const,
    latestVersion: (workspaceId: string, agentId: string) =>
      ["workspaces", workspaceId, "agents", agentId, "version", "latest"] as const,
  },

  teams: {
    all: (workspaceId: string) => ["workspaces", workspaceId, "teams"] as const,
    detail: (workspaceId: string, teamId: string) =>
      ["workspaces", workspaceId, "teams", teamId] as const,
    sessions: (workspaceId: string, teamId: string) =>
      ["workspaces", workspaceId, "teams", teamId, "sessions"] as const,
    session: (workspaceId: string, teamId: string, sessionId: string) =>
      ["workspaces", workspaceId, "teams", teamId, "sessions", sessionId] as const,
    events: (workspaceId: string, teamId: string, sessionId: string) =>
      ["workspaces", workspaceId, "teams", teamId, "sessions", sessionId, "events"] as const,
    handoffs: (workspaceId: string, teamId: string, sessionId: string) =>
      ["workspaces", workspaceId, "teams", teamId, "sessions", sessionId, "handoffs"] as const,
    communications: (workspaceId: string, teamId: string, sessionId: string) =>
      [
        "workspaces",
        workspaceId,
        "teams",
        teamId,
        "sessions",
        sessionId,
        "communications",
      ] as const,
    analytics: (workspaceId: string, teamId: string) =>
      ["workspaces", workspaceId, "teams", teamId, "analytics"] as const,
  },

  integrations: {
    catalog: (workspaceId: string, filters: { category?: string; q?: string } = {}) =>
      ["workspaces", workspaceId, "integrations", "catalog", filters] as const,
    installed: (workspaceId: string) =>
      ["workspaces", workspaceId, "integrations"] as const,
    detail: (workspaceId: string, installedServerId: string) =>
      ["workspaces", workspaceId, "integrations", installedServerId] as const,
    credentials: (workspaceId: string, installedServerId: string) =>
      ["workspaces", workspaceId, "integrations", installedServerId, "credentials"] as const,
    permissions: (workspaceId: string, installedServerId: string, agentId?: string) =>
      [
        "workspaces",
        workspaceId,
        "integrations",
        installedServerId,
        "permissions",
        agentId ?? null,
      ] as const,
    calls: (workspaceId: string, filters: Record<string, string | undefined> = {}) =>
      ["workspaces", workspaceId, "integrations", "runtime", "calls", filters] as const,
    metrics: (workspaceId: string, installedServerId?: string) =>
      [
        "workspaces",
        workspaceId,
        "integrations",
        "runtime",
        "metrics",
        installedServerId ?? null,
      ] as const,
  },

  knowledge: {
    all: (workspaceId: string) => ["workspaces", workspaceId, "knowledge-bases"] as const,
    detail: (workspaceId: string, knowledgeBaseId: string) =>
      ["workspaces", workspaceId, "knowledge-bases", knowledgeBaseId] as const,
    documents: (workspaceId: string, knowledgeBaseId: string) =>
      ["workspaces", workspaceId, "knowledge-bases", knowledgeBaseId, "documents"] as const,
  },
} as const;
