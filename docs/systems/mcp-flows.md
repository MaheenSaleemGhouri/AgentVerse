# MCP Flows — Authentication, Tool Execution, and Runtime

Sequence diagrams for the three flows in Phase 6 whose ordering carries
security weight. Companion to
[mcp-integrations.md](./mcp-integrations.md) (the architecture) and the
[threat model](../security/threat-model-tool-execution.md).

## 1. Install and authenticate

```mermaid
sequenceDiagram
    actor Admin
    participant Web as Next.js
    participant API as FastAPI
    participant Vault as Credential vault
    participant DB as Postgres

    Admin->>Web: Browse marketplace
    Web->>API: GET /integrations/catalog
    API-->>Web: entries with availability + required_credentials
    Note over Web: custom_required entries render<br/>with Install disabled and the reason

    Admin->>Web: Install (official/community only)
    Web->>API: POST /integrations {mcp_server_id}
    Note over API: No command, no endpoint accepted —<br/>both come from the catalog row
    API->>DB: INSERT installed_servers (status=pending_auth)
    API-->>Web: 201, "needs credentials"

    Admin->>Web: Paste secret
    Web->>API: PUT /{id}/credentials {key, value}
    API->>Vault: seal(value, aad=workspace|server|key)
    Vault-->>API: ciphertext + wrapped DEK
    API->>DB: UPSERT credentials (ciphertext only)
    API->>DB: UPDATE status = active
    API-->>Web: 201 {hint: "••••x7f2"}
    Note over Web: The plaintext is now unreachable.<br/>No endpoint returns it.
```

**Why `pending_auth` rather than `active`:** an integration that looks
ready and fails on first use is worse than one that says what it needs.
The status flips automatically when the credential lands — making the
admin flip a second switch would be ceremony.

## 2. Tool execution

The ordering is the design. Each step is cheaper than the one after it,
and each can only be reached by passing the ones before.

```mermaid
sequenceDiagram
    participant Model as LLM
    participant SDK as Agents SDK
    participant Gov as GovernedMcpServer
    participant B as execute_tool
    participant Redis
    participant Egress as Egress guard
    participant MCP as Third-party server
    participant DB as Postgres

    Model->>SDK: call list_issues{repo:"x"}
    SDK->>Gov: call_tool(...)
    Note over Gov: The SDK dispatches tools itself,<br/>so governance lives INSIDE the server

    Gov->>B: execute_tool(tool, args, grant, ctx)

    B->>Redis: breaker state?
    alt open
        Redis-->>B: open
        B->>DB: tool_calls (circuit_open)
        B-->>Gov: refusal the model can read
    end

    B->>B: grant.permits(tool)?
    Note over B: read_only + mutating tool → refused,<br/>independent of the model's judgment
    alt denied
        B->>DB: tool_calls (denied, reason)
        B-->>Gov: refusal
    end

    B->>B: validate args vs declared schema
    B->>Redis: per-run budget consume
    B->>Redis: cache hit?

    B->>MCP: invoke (via SDK, timeout-bounded)
    MCP->>Egress: every HTTP hop
    Note over Egress: resolve → validate ALL addresses →<br/>pin → re-validate redirects
    alt destination denied
        Egress-->>B: EgressDeniedError
        B->>DB: tool_calls (denied, reason)
        Note over B: Not retried, not counted against<br/>the breaker — a denial is not a failure
        B-->>Gov: refusal
    end

    MCP-->>B: result
    B->>B: cap + wrap as untrusted
    B->>Redis: breaker success, cache put
    B->>DB: tool_calls (success)
    B-->>Gov: CallToolResult
    Gov-->>SDK: wrapped, delimited content
    SDK-->>Model: "<tool_result> … </tool_result>"
```

**Every branch writes a row.** A blocked SSRF attempt that left no trace
would make the egress control unauditable, which is most of its value.

**Refusals return, they do not raise.** An agent told *why* a tool was
refused can choose another approach; an exception ends the run.

## 3. Run-time attachment and degradation

```mermaid
sequenceDiagram
    participant Job as agent_run_job
    participant Repo as IntegrationRepository
    participant Vault
    participant Mgr as McpConnectionManager
    participant A as GitHub (up)
    participant Bad as Internal server (down)
    participant Trace as Run trace

    Job->>Repo: resolve_for_agent(workspace, agent)
    Repo->>Vault: open() each credential
    Note over Repo: Bound by AAD — a ciphertext from<br/>another workspace fails to decrypt
    Repo-->>Job: [spec+grant, spec+grant]

    Job->>Mgr: connect_all(specs)
    par
        Mgr->>A: connect + list_tools
        A-->>Mgr: 12 tools
    and
        Mgr->>Bad: connect
        Bad--xMgr: timeout
    end

    Mgr-->>Job: [healthy, unreachable(reason)]
    Job->>Trace: mcp_server_attached {github, 12 tools}
    Job->>Trace: mcp_server_unavailable {internal, "did not respond within 25s"}

    Note over Job: The run proceeds with GitHub's tools.<br/>The dead server cost its own tools, nothing else.

    Job->>Job: Agent(mcp_servers=[GovernedMcpServer(github)])
    Note over Job: finally: manager.aclose()<br/>Per-run connections — a pooled session<br/>would outlive the credential that opened it
```

This is the phase's acceptance criterion made concrete: *a failing MCP
server disables only its own tools for that run, with a clear trace
event — it never crashes the run.*

## 4. Egress validation

The part that is easy to get subtly wrong.

```mermaid
flowchart TD
    U[URL from a tool or MCP endpoint] --> S{scheme in http/https?}
    S -->|no| D1[DENY: scheme not permitted]
    S -->|yes| C{credentials in URL?}
    C -->|yes| D2[DENY: embedded credentials]
    C -->|no| L{literal IP?}
    L -->|yes| V
    L -->|no| R[Resolve hostname]
    R --> V{EVERY address routable?}
    V -->|any private/link-local/<br/>loopback/mapped| D3[DENY: names the range]
    V -->|all public| P[Pin validated IP]
    P --> H[Connect, original Host header]
    H --> RD{redirect?}
    RD -->|yes| U
    RD -->|no| OK[Proceed]
```

Three properties, each closing a real bypass:

| Property | Bypass it closes |
| --- | --- |
| Validate **every** resolved address | A hostname with one public and one private A record |
| **Pin** the validated IP | DNS rebinding — the second resolution inside the HTTP client |
| Re-validate **each redirect hop** | `302 → 169.254.169.254`; MCP's client follows redirects by default |

Unwrapping `::ffff:169.254.169.254` and `2002:a00:1::` matters for the
same reason: the metadata address wearing a different hat is still the
metadata address.
