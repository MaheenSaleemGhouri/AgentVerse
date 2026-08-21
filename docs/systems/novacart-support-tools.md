# NovaCart Support & Commerce Tools (Phase 13)

Decisions: [ADR-0020](../adr/0020-novacart-support-tools-on-the-first-party-mcp-server.md). Builds on the MCP server surface in [ADR-0017](../adr/0017-agentverse-mcp-server-surface.md) and the tool-execution boundary in [mcp-integrations.md](mcp-integrations.md)/[ADR-0010](../adr/0010-mcp-integration-and-tool-execution-boundary.md).

## The 5 tools

All live in `orchestration_service/interface/mcp_server/tools.py`, the same file/server as the original 7 (ADR-0017). Each is a thin adapter — resolve identity, check role, call an existing application/repository method, audit, return a sanitized result.

| Tool | Role floor | Mutating | What it does |
|---|---|---|---|
| `create_support_ticket` | `member` | yes | Creates a `support_tickets` row, immediately `triaged`, no async sub-run. |
| `escalate_to_human` | `member` | yes | Same path, `category="escalation"`, `priority="urgent"` (or caller-supplied). Records the escalation as a ticket; performs no sensitive action itself. |
| `lookup_order` | `viewer` | no | Checks for an active commerce integration; returns `{"available": false, ...}` today (see "Commerce tools" below). |
| `check_shipping_status` | `viewer` | no | Same as `lookup_order`. |
| `request_return` | `member` | yes | **Always** creates a `category="return-request"` approval ticket — never processes a return automatically, regardless of integration state. |

## Support-ticket flow

```
Customer → NovaCart Agent → create_support_ticket (MCP tool)
  → Governed Tool Boundary (apps/worker/tools/boundary.py)
  → SupportTicketService.create_ticket_direct (application)
  → SqlSupportTicketRepository (existing repository methods)
  → support_tickets row, status=triaged
  → sanitized {ticket_id, status, category, priority, created_at}
  → Agent → Customer
```

`create_ticket_direct` is a new application-service method, added alongside the existing `create_ticket` (used by the human-facing REST API, which triggers a real async triage-agent run). The tool path skips that indirection because the calling agent has already classified the issue live in conversation — it uses only the existing `TRIAGED` status and the existing, unconstrained free-text `category`/`priority` columns. No schema change.

## Escalation flow

Identical to ticket creation, tagged `category="escalation"`/`priority="urgent"` — there is no separate "escalated" status in `TicketStatus` (`triaging|triaged|resolved|failed` only), and none was added. A human support queue filters on `category`/`priority`, the same fields Phase 8's own `support-triage` golden examples already populate with these exact conventions.

## How NovaCart actually gets these tools at run time

NovaCart's agent is configured as if AgentVerse's own `/mcp` server were a third-party MCP integration it installed:

- `installed_servers` row (`mcp_server_id=NULL`, custom install) pointing at the API's own `/mcp` endpoint.
- A real `mcp_client`-kind `api_keys` credential, sealed into `credentials` via the existing `CredentialVault` — same as any real integration's secret.
- A `permissions` row scoping NovaCart's `agent_id` to `allowed_tools=["create_support_ticket","escalate_to_human","lookup_order","check_shipping_status","request_return"]`.

At run time, `attach_integrations()` connects NovaCart to this "integration" exactly like any other, and every call is governed by the existing `execute_tool` boundary — permission check, argument validation, per-run budget, retry/backoff, result sanitization, `tool_calls` logging — unmodified. See ADR-0020 for why this reuses 100% of existing infrastructure instead of adding a native/second registry.

## Commerce tools — **AgentVerse does not store native e-commerce order data**

**Order-related capabilities require an authorized external commerce integration/MCP server** (e.g. Shopify — already cataloged in `mcp_catalog.py`, `slug="shopify"`). No orders/order_items/customers tables exist in this codebase, deliberately — a prior audit confirmed none were needed and none should be fabricated.

This phase ships the tool *surface* only:

- `lookup_order`/`check_shipping_status` check whether any active `installed_servers` row exists for the workspace. If none, they return `{"available": false, "reason": "No commerce integration is installed for this workspace."}`. If one exists (none does, in any environment today), they return `{"available": false, "reason": "...live order lookup through it is not yet wired..."}` — honest either way, never a fabricated order/status/tracking number/delivery date.
- The actual outbound call to a real commerce MCP server (Shopify or otherwise) is **not built yet**. No real commerce credentials exist anywhere to develop or test that call against — guessing at a third party's real tool/argument shapes without them would ship unverifiable code. This is the one genuinely open follow-up item from Phase 13.
- `request_return` never depends on any of the above — it always routes to a human-approval ticket, per the product policy that no autonomous return/refund action exists in this codebase.

## Permissions

No new permission-enum system. The task's conceptual permission names map onto the existing `permissions`/`ToolGrant` mechanism:

| Conceptual name | Real mechanism |
|---|---|
| `CREATE_SUPPORT_TICKET`, `ESCALATE_SUPPORT`, `REQUEST_RETURN` | tool name in `permissions.allowed_tools`; install's `level=full` (each tool is `is_mutating=True`) |
| `READ_ORDER`, `READ_SHIPPING_STATUS` | tool name in `permissions.allowed_tools`; works even at `level=read_only` (`is_mutating=False`) |

## Security notes

- `workspace_id` is always resolved from the MCP credential's own claims, never accepted as a tool argument — the existing `resolve_context`/`require_role` machinery, unchanged.
- Tool argument schemas accept only their documented fields (`order_number`, `subject`, `body`, `category`, `priority`, `reason`, `summary`) — never `workspace_id`, `credential_id`, an MCP server URL, or an API key, and the existing `validate_arguments`'s `additionalProperties: false` check rejects anything else.
- Every call — success, denial, and the commerce tools' "unavailable" outcome — writes an audit row through the existing `AuditService`, same as the original 7 tools.
- Results returned to the model never include ticket bodies, internal user ids beyond the ticket's own id, credentials, or raw external payloads.

## Known follow-up (explicitly not done this phase)

Real outbound calling to a connected commerce MCP server (Shopify or equivalent) for `lookup_order`/`check_shipping_status`. Requires: a real workspace with a real commerce integration installed and credentialed, then building the actual MCP-client call inside these two tool functions against that server's real, discovered tool schema — not guessed in advance.
