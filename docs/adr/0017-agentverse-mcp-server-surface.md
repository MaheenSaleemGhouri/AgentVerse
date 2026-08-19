# ADR-0017: AgentVerse's Own MCP Server Surface

## Context

`docs/roadmap.md`'s Phase 12 calls for AgentVerse to expose itself *as* an MCP server, not only consume other MCP servers (ADR-0010's integration stack). An audit confirmed this was genuinely greenfield: no `mcp` server-side dependency anywhere, no server-exposing routes, zero prior art to reuse beyond the general shape of "adapter delegates to an existing application function" that ADR-0016's workflow engine already established for Phase 9's primitives.

Three things had to be decided: what protocol library to build on, how a caller authenticates, and how to bound the exposed surface so this isn't a backdoor around the platform's existing permission model.

## Decision

### Build on the official `mcp` Python SDK, never a hand-rolled JSON-RPC layer

Added as a real dependency (`apps/api/pyproject.toml`), mirroring how the client side already uses the OpenAI Agents SDK's built-in MCP client rather than hand-rolling the protocol. `FastMCP` (the SDK's ASGI-app-producing server primitive) is used with Streamable HTTP — the current MCP spec's recommended remote transport — not stdio, since this is a hosted, multi-tenant server, not a local subprocess per caller.

### One route, `POST /mcp`, workspace resolved from the credential — never the URL

Matches how `api_keys` already work: a key is scoped to a workspace at issuance, not re-derived from a path segment on every call. This avoids a class of bug a URL-encoded tenant id invites (a caller editing the URL to point at a different workspace id) — the credential alone determines the workspace, and there is no workspace id anywhere in the request for a caller to even attempt to forge.

### `api_keys.kind` distinguishes MCP credentials from REST credentials — same table, same service, new column

`api_keys` gained a `kind` column (`'user_api_key' | 'mcp_client'`, migration `8c1d444558ec_phase_12_api_key_kind`) rather than a parallel table. `ApiKeyService`'s hash/scope/revoke/rotate logic is reused verbatim — genuinely one credential system, not two. `ApiKeyTokenVerifier` (`mcp_server/auth.py`) rejects any key whose `kind` is not `mcp_client` with the same non-distinguishing failure used for an unknown or revoked key (CLAUDE.md §10 — no oracle for "right key, wrong door"), and the reverse is enforced too: `get_current_workspace`'s REST branch already only accepts `user_api_key`. A leaked MCP integration token cannot be replayed against the REST API, and vice versa.

Role resolution reuses `effective_role(key.scope, membership.role)` — the exact function the REST API-key path already calls — so a `read_only`-scoped MCP credential is capped at viewer through the same ceiling logic, not a second permission model that could silently drift from the first.

### Exactly 7 tools, each a thin adapter — no arbitrary API exposure

`list_agents`, `get_agent`, `run_agent` (tool name `run_agent_tool` — `run_agent` collides with the imported application function of the same name in the same module), `get_run_status`, `list_workflows`, `get_workflow`, `run_workflow`. Every tool calls the identical application function or repository method its REST-route equivalent already calls (`run_agent()`, `execute_workflow()`, `SqlAgentRepository`, `SqlWorkflowRepository`, `SqlAgentRunRepository`, `SqlWorkflowRunRepository`) — the same "delegate, never reimplement" principle ADR-0016 used for the workflow engine. This is a closed list, not a generic database/API passthrough: CLAUDE.md §10's AI-specific threat-surface rule (no unbounded surface for an external, untrusted caller) applies naturally to an MCP server, since its whole purpose is to be called by an external agent the workspace does not fully control.

Read tools require `viewer`; `run_agent_tool`/`run_workflow` require `member` and enforce the same `QuotaExceededError` path the REST run-submission routes already enforce (`QuotaService.enforce`, `MeteredDimension.AGENT_RUNS`/`WORKFLOW_EXECUTIONS`) — an MCP-triggered run is metered identically to a REST-triggered one, not a free side channel around billing.

### Every tool call is audited — success, denial, not-found, and quota-exceeded alike

`mcp_server.tool_executed` / `mcp_server.tool_denied`, carrying `{mcp_client_id}` in metadata, written through the same `AuditService` every other subsystem uses — not new audit infrastructure. A denial is audited *before* the `McpAuthorizationError` propagates (deny-then-log, matching `require_role`'s existing pattern), so a permission ceiling being hit is never silently swallowed.

### DNS-rebinding protection is kept enabled, and explicitly configured — never disabled

The SDK's `TransportSecurityMiddleware` defends against DNS-rebinding by validating the `Host`/`Origin` headers on every request. `FastMCP` only auto-populates a (loopback-only) default allowlist when its `host=` constructor argument is itself a loopback address — which this server never sets, since it isn't bound to a literal host at the ASGI level, it's mounted into the existing FastAPI app. Left unconfigured, the resolved allowlist would have stayed loopback-only forever, meaning a genuinely deployed `/mcp` would reject **100% of real remote traffic** with `421 Misdirected Request` — a real production gap, caught by writing this server's tests against the real SDK security middleware rather than a fake that would have let it pass. The fix (`server.py`'s `_transport_security`) derives the real public host from `settings.api_public_url` and adds it to the allowlist — both a bare (no-port, matching a request over the scheme's default port, where a `Host` header omits the port) and a `:*`-wildcard (matching an explicit port) entry, since the SDK's matcher does exact-or-wildcard matching only, with no implicit port-optionality. Localhost/127.0.0.1/::1 entries are preserved (in both forms) for local dev. `enable_dns_rebinding_protection` is never set to `False` — the correct fix for a real host being rejected is adding that host to the allowlist, not turning the protection off (CLAUDE.md's "never weaken security" default).

### Mounted at the FastAPI app's root, not at an additional `/mcp` prefix

`FastMCP`'s sub-app already declares its own route at `/mcp` internally (the SDK default `streamable_http_path`). Mounting it *again* under `app.mount("/mcp", mcp_asgi_app())` would make a bare `POST /mcp` hit only the `Mount`'s own prefix boundary — Starlette redirects that exact case to add a trailing slash (307 to `/mcp/`) regardless of what path the child app declares internally, because the computed child `route_path` for an exact-prefix hit is an empty string, which never matches a `Route` (always `/`-prefixed). A real MCP client POSTing a streamed body to `/mcp` and not following redirects on a POST would break. `main.py` instead mounts at the app's root (`app.mount("/", mcp_asgi_app())`), so the sub-app's own `/mcp` route is reached directly, with zero redirect hops — verified empirically (Starlette `TestClient`) to not shadow any other route (routes already registered earlier in `main.py` are matched first, in registration order) and to preserve correct 404 behavior for genuinely unmatched paths.

### Location: inside `orchestration_service`, not a new bounded context

`orchestration_service/interface/mcp_server/{server.py,tools.py,auth.py,context.py}` — this is a new protocol adapter over existing capabilities (agents, runs, workflows all already live in `orchestration_service`), not a new datastore or a new owned entity. Mirrors ADR-0016's reasoning for keeping the workflow engine inside `orchestration_service` rather than splitting a service out for it.

## Consequences

- `api_keys.kind` is a breaking-safe additive column (`NOT NULL DEFAULT 'user_api_key'`) — every pre-existing key is unambiguously a REST credential post-migration, no backfill ambiguity.
- The MCP-clients settings page (issue/list/revoke `kind='mcp_client'` keys) is a near-direct copy of the existing API-keys settings page's list/revoke/issue-dialog pattern — no new UI pattern invented.
- A workspace's MCP surface is exactly as capable as its lowest-privilege REST equivalent — no tool exists that has no REST analogue, so there is no way to reason about "what can an MCP client do" separately from "what can an API key do."
- The transport-security allowlist is derived from one setting (`api_public_url`) — a future change to the API's public hostname (e.g. a custom domain) requires only updating that setting, not a code change here.

## Alternatives considered and rejected

- **A hand-rolled Streamable HTTP/JSON-RPC implementation.** Rejected: the `mcp` SDK is the vetted reference implementation of a spec this codebase does not otherwise need to track version-by-version; hand-rolling it would be exactly the kind of avoidable protocol-correctness risk a fake test could hide.
- **A separate `mcp_client_keys` table, parallel to `api_keys`.** Rejected: would duplicate hash/scope/revoke/rotate logic `ApiKeyService` already owns — a second thing to keep in sync, for no isolation benefit a `kind` column doesn't already give.
- **Workspace id in the `/mcp` URL path (e.g. `/workspaces/{id}/mcp`).** Rejected: reintroduces exactly the "trust a client-supplied workspace id" pattern CLAUDE.md §7/§10 forbid elsewhere (`workspace_id` always resolved from the authenticated identity/credential, never from client input) — the credential alone must determine the workspace.
- **Disabling DNS-rebinding protection to make the 421 go away.** Rejected outright as a weakening of a real security control; the correct fix is configuring its allowlist with the real production host, which was the fix shipped.
- **A generic passthrough tool (e.g. "call any REST endpoint").** Rejected: defeats the entire purpose of a closed, auditable tool surface and would hand an external MCP client the same blast radius as a full-scope API key without the caller ever seeing that tradeoff.
