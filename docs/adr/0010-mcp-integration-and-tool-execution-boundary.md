# ADR 0010: MCP Integration, the Tool-Execution Boundary, and the Server Catalog

## Status

Accepted. Implements `docs/roadmap.md` **Phase 6** (Tool-Calling, Central
Tool-Execution Boundary & MCP).

> **Numbering note.** This work was requested as "Phase 7". The
> roadmap's Phase 7 is *Billing & Stripe Integration*; tool calling and
> MCP are Phase 6. The implementation matches the request; the label
> follows the roadmap so the repo's own sequencing stays coherent. Same
> convention as ADR-0009.

Threat model:
[`docs/security/threat-model-tool-execution.md`](../security/threat-model-tool-execution.md).

## Context

The platform can build agents (Phase 4), ground them in documents
(Phase 5), and run them in teams (Phase 9). It cannot yet let them *act*
on anything outside itself.

Five decisions had to be settled before code, because each has a
convenient answer that is wrong in a way nothing would report.

## Decision

### We do not write per-provider integrations. We write one MCP client.

The brief lists ~38 services to "implement support for". Implementing 38
connectors is precisely what MCP exists to prevent, and contradicts the
brief's own stated principle ("use MCP whenever an official MCP server
already exists").

So: **one** client, and a **catalog** of server definitions.

A catalog entry is data — transport, auth scheme, package or URL,
declared tool categories, documentation link. Adding a server is a row,
not a module. `mcp_servers` is that catalog; `installed_servers` is a
workspace's installation of a catalog entry (or of its own custom
server).

Catalog entries carry an honest `availability`:

| Value | Means |
| --- | --- |
| `official` | A first-party MCP server exists and is maintained by the vendor |
| `community` | A third-party MCP server exists; quality is not vendor-backed |
| `custom_required` | No MCP server exists today; the user must supply their own endpoint |

This field is load-bearing for honesty. Several services on the brief's
list have no MCP server at present. Seeding them as installable would
produce a marketplace that lies — a user clicks Install and gets a
connection that can never succeed. `custom_required` says so on the card.

### The client wraps the SDK's MCP support; it does not reimplement it

The OpenAI Agents SDK ships `MCPServerStdio`, `MCPServerSse`,
`MCPServerStreamableHttp`, `MCPServerManager`, `MCPUtil`, and
`ToolFilter`/`create_static_tool_filter`. All of it is used. AgentVerse
writes no protocol code, no JSON-RPC framing, no tool-schema translation
of its own.

What AgentVerse adds is everything the SDK has no notion of: which
workspace this connection belongs to, where its credentials come from,
which destinations are permitted, what a tool call costs, and what gets
recorded.

Per-tool enable/disable maps to the SDK's own `ToolFilter` rather than a
hand-written filter, so an agent's allowed-tool list is enforced by the
same code path the SDK uses for everything else.

### Transport follows the trust boundary, and is not the user's free choice

`stdio` spawns a local process. Offering it for arbitrary user-supplied
commands would be remote code execution on the worker fleet with extra
steps.

Therefore: `stdio` is permitted **only** for catalog entries AgentVerse
has vetted, whose command and arguments come from the catalog row — never
from user input. A custom server registered by a user is remote by
definition and gets `sse` or `streamable_http`, through the egress guard.

This is a narrower rule than "choose the transport that fits", and it is
narrower on purpose.

### Everything goes through one boundary, including SDK-wrapped tools

`execute_tool` is the single choke point: permission check, argument
validation against the declared schema, credential resolution, egress
guard, timeout, output cap, untrusted-output delimiting, `tool_calls`
logging.

Native built-in tools route through it too. A "trusted" bypass for
first-party tools would mean the audit log has holes exactly where
someone would look first, and would create a second code path that drifts
from the reviewed one.

The permission check is **independent of the model's judgment**. The
model selects a tool; AgentVerse decides whether that selection is
allowed. A read-only grant makes a write tool uncallable regardless of
what any injected text argues.

### Credentials are write-only through the API and encrypted at rest

`credentials` stores ciphertext under envelope encryption: a per-row data
key, itself encrypted by a key from the runtime environment. A database
dump alone yields nothing usable.

No endpoint returns a credential value. Not masked, not partial — the
read path does not exist. Callers can create, rotate, and delete. This is
the same discipline Phase 1 applied to API keys, extended to third-party
secrets, and it is why `credentials` has no `GET /{id}/value` route to
review: there is nothing to get wrong.

Resolution happens at call time inside the boundary, keyed by the
authenticated workspace. Credentials never enter a job payload, an agent
config, or a log line.

## Consequences

- Eleven new tables. `tool_calls`, `tool_logs`, and `tool_metrics` are
  high-volume and partitioned by `created_at` from their first
  migration, matching `agent_run_steps` and `execution_events`.
- `tool_calls` is deliberately separate from `agent_run_steps` even
  though a tool call is a kind of step. A tool call has arguments, a
  result, a target server, a credential reference, and a permission
  decision — none of which fit `agent_run_steps.payload` without making
  that column a union type. The trace UI joins them; the tables stay
  typed.
- A tool call is recorded **even when denied**. A blocked SSRF attempt
  that left no row would make the control unauditable, which is most of
  its value.
- `installed_servers` references `mcp_servers` with `ON DELETE RESTRICT`:
  removing a catalog entry a workspace has installed must fail loudly.
- Custom servers have a null `mcp_server_id` and carry their own
  endpoint. The nullable FK is the price of not duplicating the table.
- Marketplace entries are global (no `workspace_id`) — the catalog is
  platform data. Everything else in this phase is tenant-scoped, and
  `mcp_servers` is called out here precisely because a table without
  `workspace_id` is normally a bug (CLAUDE.md §8).
- `oauth_sessions` rows are short-lived and carry a PKCE verifier. They
  are deleted on completion, not kept — a stale verifier is a credential.

## Alternatives considered and rejected

- **Write 38 bespoke connectors.** Rejected: it is the problem MCP
  solves, it does not scale past the initial list, and every connector
  is separate code to secure.
- **Hand-roll an MCP client** for control over the protocol. Rejected
  outright: the SDK provides it, and the brief forbids recreating SDK
  functionality. A second protocol implementation is a second place for
  a parsing bug.
- **Let users choose `stdio` for their own servers.** Rejected: that is
  arbitrary command execution on the worker fleet.
- **A "trusted" fast path for built-in tools**, skipping the boundary.
  Rejected: two code paths, and the audit log develops holes.
- **Store credentials in `installed_servers.config` as JSONB**, like
  agent config. Rejected: config is readable by every endpoint that
  returns a server; a secret in it leaks the first time someone renders
  the settings screen.
- **Return masked credentials** (`sk-...abcd`) for display. Rejected: a
  prefix plus a suffix is a meaningful search key, and building the read
  path at all is what later gets loosened.
- **Reuse `agent_run_steps` for tool calls.** Rejected: it would make
  `payload` a union and lose per-column indexing on the fields the
  runtime dashboard filters by.
