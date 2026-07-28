# MCP Integrations & the Tool-Execution Boundary

How AgentVerse agents reach external systems. Implements
`docs/roadmap.md` Phase 6; decisions in
[ADR-0010](../adr/0010-mcp-integration-and-tool-execution-boundary.md);
threat model in
[threat-model-tool-execution.md](../security/threat-model-tool-execution.md).

> **Numbering.** Requested as "Phase 7"; the roadmap's Phase 7 is
> Billing, and this content is Phase 6. Same convention as ADR-0009.

## The one-sentence version

AgentVerse writes **no MCP protocol code**. The OpenAI Agents SDK
provides the client; AgentVerse decides who may connect to what, with
which credentials, under which limits, and records everything.

## Architecture

```
apps/api                              apps/worker
├─ domain/integration_entities.py     ├─ mcp/
├─ domain/ports/                      │   ├─ factory.py     build SDK MCPServer
│   integration_repository.py         │   ├─ transport.py   egress-guarded httpx
├─ infrastructure/                    │   ├─ manager.py     connect · discover · health
│   integration_repository.py         │   ├─ governed.py    boundary INSIDE an MCPServer
├─ application/                       │   ├─ attach.py      graceful degradation
│   ├─ mcp_catalog.py   38 entries    │   ├─ repository.py  resolve grants + credentials
│   └─ seed_catalog.py                │   └─ tables.py
└─ interface/routers/integrations.py  └─ tools/
                                          ├─ boundary.py    the choke point
packages/python-shared                    └─ policy.py      breaker · cache · budget
└─ security/
    ├─ egress_guard.py    deny-by-default outbound
    ├─ envelope.py        credential encryption
    └─ untrusted.py       the one delimiting renderer
```

## Why there are no per-service integrations

The brief listed ~38 services to "implement support for". Implementing 38
connectors is what MCP exists to prevent.

So: **one client, and a catalog**. A catalog entry is data — transport,
auth scheme, package or URL, documentation link. Adding a service is a
row in `mcp_catalog.py`, not a module.

Entries carry an honest `availability`:

| Value | Count | Means |
| --- | --- | --- |
| `official` | 18 | The vendor publishes and maintains an MCP server |
| `community` | 11 | A third party does; quality is not vendor-backed |
| `custom_required` | 9 | **No MCP server exists today** |

The third value is the important one. WhatsApp, Twilio, Salesforce,
Teams, Outlook, Dropbox, OneDrive, Google Docs, and Google Cloud have no
installable first-party MCP server. Seeding them as installable would
produce a marketplace that lies — a user clicks Install, enters a
credential, and gets a connection that can never succeed. Their cards
render with the reason and a disabled Install button instead. A test
asserts the field is not uniformly optimistic: if every entry claimed
`official`, it would be decoration.

## The tool-execution boundary

Everything goes through `tools/boundary.py::execute_tool` — native
built-ins, MCP tools, SDK-wrapped tools. There is no trusted fast path:
a bypass would put holes in the audit log exactly where an investigator
looks first, and create a second code path that drifts from the reviewed
one.

Order of operations, cheapest first:

| # | Step | Why here |
| --- | --- | --- |
| 1 | Circuit breaker | Skipping it means paying for the rest to reach a dead server |
| 2 | Permission | Independent of the model's judgment — a `read_only` grant makes a write tool uncallable whatever an injected instruction argues |
| 3 | Argument validation | Tool arguments are model output, and model output is untrusted input |
| 4 | Per-run budget | Bounds a tool loop earlier and more cheaply than the run's own ceilings |
| 5 | Cache | Answer without a network call where the grant permits |
| 6 | Execute | Bounded by timeout, with retries and backoff |
| 7 | Sanitise | Cap and wrap before it re-enters the model's context |

**Every path writes a `tool_calls` row, including denials.** `denied` and
`circuit_open` are first-class statuses. A blocked SSRF attempt that left
no trace would make the egress control unauditable, which is most of its
value.

A denial is **returned, not raised** — the agent is told why and can pick
another approach, where an exception would end the run.

### How MCP tools get governed

The SDK calls `server.call_tool()` itself. A boundary sitting *beside*
the SDK would govern native tools and silently miss every MCP one — the
larger surface.

So the boundary moved **inside**. `GovernedMcpServer` subclasses the
SDK's `MCPServer`, delegates connect/name/cleanup/discovery/prompts
straight through, and overrides exactly one method. `attach_integrations`
is the only path that builds them, so an `Agent` never holds a raw SDK
server. "Nothing bypasses the boundary" is structural, not a convention.

## Egress control (threat model T1)

Deny-by-default for every agent-initiated outbound call. Three properties
make it more than an IP blocklist:

1. **Every resolved address is validated**, not just the first — a
   hostname with several A records where one is public is otherwise a
   trivial bypass.
2. **The validated address is pinned.** The caller dials the approved IP
   with the original `Host` header rather than handing the hostname back
   to a client that resolves it a second time. That second resolution is
   DNS rebinding, and validate-then-fetch does not stop it.
3. **Redirects are re-validated.** MCP's default HTTP client sets
   `follow_redirects=True`, so a URL-only pre-flight never sees the hop
   that matters. The guard therefore lives in the httpx **transport**,
   which is invoked once per hop.

Denied: loopback, RFC1918, `169.254/16` (including the cloud metadata
address), CGNAT, IPv6 loopback/link-local/ULA, IPv4-mapped and 6to4
wrappings of all of the above, and every scheme except `http`/`https`.

Two layers: this, plus worker egress network policy at the infrastructure
layer. Neither is trusted alone.

## Credentials

Envelope encryption. A per-credential data key encrypts the secret with
AES-256-GCM; a key-encryption key from the environment encrypts that data
key. A database dump — the realistic breach — yields nothing usable.

The ciphertext is bound to its row via AAD
(`workspace | server | key`), so a ciphertext copied into another
workspace's row **fails to decrypt** rather than handing over a working
credential.

**There is no read path.** No repository method, no domain field, no
response schema, no endpoint returns a credential value — not masked, not
`sk-...abcd`. `hint` is the last four characters, never a prefix: `sk-`,
`ghp_`, and `xoxb-` identify a key's kind and issuer, while the tail only
answers "is this the one I pasted?".

### Configuration

`AGENTVERSE_CREDENTIAL_KEK_V1`, 32 raw bytes base64-encoded. Read by
**both** apps/api (which writes) and apps/worker (which resolves) — hence
deliberately not service-prefixed. Two different values would make
ciphertext written by one unreadable by the other.

```bash
python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
```

There is no fallback and no development default. A missing key fails
startup loudly (Rule 1). Rotation: add `..._V2`, switch the active
version; existing rows stay readable under V1 until a rewrap sweep moves
them, so it is not a hard cutover.

## Transports

| Transport | Available to | Why |
| --- | --- | --- |
| `stdio` | **Vetted catalog entries only** | Spawns a local process. A user-supplied command is remote code execution on the worker fleet with extra steps. |
| `sse`, `streamable_http` | Anything | Remote, through the egress guard. |

A user-registered server is remote by definition. The API's
`RegisterCustomServerRequest` excludes `stdio` at the *type* level, so
the refusal is visible in the generated contract rather than buried in a
validator.

## Permissions

| Level | Means |
| --- | --- |
| `read_only` | Mutating tools are refused |
| `read_write` | May change data on the connected service |
| `admin` | Full access including administrative tools |

Granted to an agent, a team, or workspace-wide. An agent-specific grant
shadows the workspace-wide one for the same server: narrowing an
individual agent must not be undone by a broader default.

Per-grant limits: `timeout_seconds`, `max_retries`, `cache_ttl_seconds`,
`max_calls_per_run`, `priority` — each bounded server-side so a grant
cannot configure its way past the run's own ceilings.

### Is a tool "mutating"?

MCP has no such flag, so it is **inferred from the tool name**, and the
inference is deliberately biased: unknown tools default to mutating. A
read tool wrongly marked mutating is an annoyance a user fixes by
granting read-write; a write tool wrongly marked read-only is a
read-only grant that can modify a customer's GitHub. The failure
directions are not symmetric, so neither is the default.

The server-written **description is not consulted** as a tiebreaker — a
malicious server would describe its write tool in read-sounding language,
and a signal an attacker controls can never widen access.

## Graceful degradation

The phase's acceptance criterion: *a failing MCP server disables only its
own tools for that run, with a clear trace event — it never crashes the
run.*

`McpConnectionManager.connect` never raises for a server-side problem.
Denied endpoint, refused transport, timeout, protocol error — each
becomes a `ConnectionResult` carrying the reason, and `attach_integrations`
turns it into an `mcp_server_unavailable` trace event. The run proceeds
with whatever connected.

Connections are **per-run, not pooled**: a pooled session would outlive
the credential that opened it, so a revoked token would keep working
until the pool happened to evict the entry. Per-run costs a handshake;
the alternative costs correctness.

## API

`/api/v1/workspaces/{workspace_id}/integrations`. `workspace_id` always
from the authenticated identity, never the path.

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/catalog` | viewer |
| `POST` | `` | **admin** |
| `POST` | `/custom` | **admin** |
| `GET` | `` · `/{id}` | viewer |
| `PATCH` · `DELETE` | `/{id}` | **admin** |
| `PUT` · `GET` · `DELETE` | `/{id}/credentials[/{key}]` | **admin** |
| `POST` · `GET` · `DELETE` | `/{id}/permissions[/{pid}]` | **member** |
| `GET` | `/runtime/calls` · `/runtime/metrics` | viewer |

Roles are deliberately not uniform. Install and credentials are admin —
an install decides which third party your agents can reach, and a
credential is a key to a customer's own GitHub. Granting is *member*,
because the set of reachable servers is already admin-gated, so a member
can only grant from what an admin approved. Requiring an admin for every
agent's tool list would make the feature unusable and pressure someone
into loosening the gate that actually matters.

Cross-workspace reads are **404, never 403** — a 403 confirms existence.

## Frontend

| Screen | Route |
| --- | --- |
| Integrations (Connected · Marketplace) | `/dashboard/{ws}/integrations` |
| Server detail (Tools · Credentials · Access · Activity) | `/dashboard/{ws}/integrations/{id}` |
| MCP runtime | `/dashboard/{ws}/mcp` |

`/mcp` is deliberately **not** a second marketplace — two screens with
the same Install button leaves users unsure which is authoritative. It
answers a different question: what have my agents been doing, and what
got refused.

The credentials panel has no reveal control and no copy button, because
there is nothing to reveal. The value input clears on save: leaving a
secret in a DOM input puts it in memory and in the next screenshot.

Denied calls are shown, not filtered out, and toned as warnings rather
than errors — a wall of legitimate refusals should not read as an outage.

## Testing

| Layer | Where | Covers |
| --- | --- | --- |
| Egress | `packages/python-shared/tests/security/test_egress_guard.py` | Metadata IP direct + via DNS, IPv4-mapped/6to4, IPv6 ranges, scheme allowlist, credentials-in-URL, mixed resolution, redirect chains |
| Crypto | `.../test_envelope.py` | Tamper detection, AAD row-binding, rotation, no-fallback-key |
| Boundary | `apps/worker/tests/tools/test_boundary.py` | Permission, argument validation, sanitisation, breaker, cache, budget, audit |
| MCP | `.../test_mcp_factory.py`, `.../test_governed_mcp.py` | stdio catalog-only, transport guard, graceful degradation, nothing bypasses the boundary |
| Catalog | `apps/api/tests/.../test_mcp_catalog.py` | Installable entries can connect; unavailable ones explain themselves; no shell in stdio args |
| API | `.../test_integrations_route.py` | Write-only credentials, install refusal, tenant isolation, denial audit |

The LLM is never called and no MCP server is contacted.

## Accepted residual risks

Restated from the threat model so they are visible here too:

1. **Persuaded use of a permitted tool.** Blast radius is the permission
   grant. Not detected, deliberately — detection does not work.
2. **SSRF through a third party's own fetch-style tool.** The request
   originates from their infrastructure, not ours.
3. **A server that turns malicious after install.** Logged and
   health-monitored, not prevented.
4. **Corporate-network MCP servers are unreachable.** An opt-in
   allowlist is deferred; blocking is the safe default.

Each is a decision, not an oversight.
