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

  members: (workspaceId: string) => ["workspaces", workspaceId, "members"] as const,

  apiKeys: (workspaceId: string) => ["workspaces", workspaceId, "api-keys"] as const,

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

  knowledge: {
    all: (workspaceId: string) => ["workspaces", workspaceId, "knowledge-bases"] as const,
    detail: (workspaceId: string, knowledgeBaseId: string) =>
      ["workspaces", workspaceId, "knowledge-bases", knowledgeBaseId] as const,
    documents: (workspaceId: string, knowledgeBaseId: string) =>
      ["workspaces", workspaceId, "knowledge-bases", knowledgeBaseId, "documents"] as const,
  },
} as const;
