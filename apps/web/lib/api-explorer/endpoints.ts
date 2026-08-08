/**
 * The endpoints the explorer offers.
 *
 * A hand-curated list rather than everything in the OpenAPI schema, and
 * that is the point: the schema has well over a hundred operations, most
 * of which nobody explores interactively. This is the set someone
 * integrating against AgentVerse actually reaches for first, in the
 * order they reach for it.
 *
 * **Read-only by construction.** Every entry here is a `GET`. An
 * explorer that could fire `POST /runs` from a form would spend a
 * customer's money on a curiosity, and one that could `DELETE` an agent
 * would do worse. Writes belong in the SDK and CLI, where the caller
 * has written the call down deliberately — the explorer's job is to let
 * someone see the *shape* of a response before they write that code.
 */

export interface ExplorerParam {
  readonly name: string;
  readonly label: string;
  readonly placeholder?: string;
  readonly required?: boolean;
}

export interface ExplorerEndpoint {
  readonly id: string;
  readonly group: string;
  readonly method: "GET";
  /** `{workspace_id}` is substituted from the active workspace. */
  readonly path: string;
  readonly summary: string;
  readonly pathParams?: readonly ExplorerParam[];
  readonly queryParams?: readonly ExplorerParam[];
}

export const EXPLORER_ENDPOINTS: readonly ExplorerEndpoint[] = [
  {
    id: "list-agents",
    group: "Agents",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/agents",
    summary: "Every agent in this workspace.",
  },
  {
    id: "get-agent",
    group: "Agents",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/agents/{agent_id}",
    summary: "One agent, by id.",
    pathParams: [{ name: "agent_id", label: "Agent ID", required: true }],
  },
  {
    id: "latest-version",
    group: "Agents",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/agents/{agent_id}/versions/latest",
    summary: "The agent's most recent version — the configuration a run would use.",
    pathParams: [{ name: "agent_id", label: "Agent ID", required: true }],
  },
  {
    id: "search",
    group: "Search",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/search",
    summary: "Search agents, knowledge bases, teams and the catalog at once.",
    queryParams: [
      { name: "q", label: "Query", placeholder: "sales", required: true },
      { name: "limit", label: "Results per kind", placeholder: "5" },
    ],
  },
  {
    id: "list-listings",
    group: "Marketplace",
    method: "GET",
    path: "/api/v1/marketplace/listings",
    summary: "The public catalog. Unauthenticated — this one works without a key.",
    queryParams: [
      { name: "q", label: "Query", placeholder: "research" },
      { name: "category", label: "Category", placeholder: "productivity" },
      { name: "sort", label: "Sort", placeholder: "popular" },
    ],
  },
  {
    id: "list-templates",
    group: "Marketplace",
    method: "GET",
    path: "/api/v1/marketplace/templates",
    summary: "The first-party template library.",
  },
  {
    id: "get-listing",
    group: "Marketplace",
    method: "GET",
    path: "/api/v1/marketplace/listings/{slug}",
    summary: "One listing, by slug.",
    pathParams: [
      { name: "slug", label: "Slug", placeholder: "research-assistant", required: true },
    ],
  },
  {
    id: "list-knowledge",
    group: "Knowledge",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/knowledge-bases",
    summary: "Knowledge bases in this workspace.",
  },
  {
    id: "list-webhooks",
    group: "Webhooks",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/webhooks",
    summary: "Registered webhook endpoints.",
  },
  {
    id: "webhook-events",
    group: "Webhooks",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/webhooks/events",
    summary: "Event types you can subscribe to.",
  },
  {
    id: "webhook-deliveries",
    group: "Webhooks",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/webhooks/deliveries",
    summary: "Recent delivery attempts, including failures and retries.",
  },
  {
    id: "usage",
    group: "Billing",
    method: "GET",
    path: "/api/v1/workspaces/{workspace_id}/billing/usage",
    summary: "This period's usage against quota.",
  },
];

/** Substitute path params and append the query string. */
export function buildPath(
  endpoint: ExplorerEndpoint,
  workspaceId: string,
  pathValues: Record<string, string>,
  queryValues: Record<string, string>,
): string {
  let path = endpoint.path.replace("{workspace_id}", workspaceId);
  for (const param of endpoint.pathParams ?? []) {
    path = path.replace(`{${param.name}}`, encodeURIComponent(pathValues[param.name] ?? ""));
  }
  const search = new URLSearchParams();
  for (const param of endpoint.queryParams ?? []) {
    const value = queryValues[param.name];
    if (value !== undefined && value !== "") search.set(param.name, value);
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

/** Whether every required parameter has a value. */
export function isComplete(
  endpoint: ExplorerEndpoint,
  pathValues: Record<string, string>,
  queryValues: Record<string, string>,
): boolean {
  const missingPath = (endpoint.pathParams ?? []).some(
    (param) => param.required === true && (pathValues[param.name] ?? "") === "",
  );
  const missingQuery = (endpoint.queryParams ?? []).some(
    (param) => param.required === true && (queryValues[param.name] ?? "") === "",
  );
  return !missingPath && !missingQuery;
}
