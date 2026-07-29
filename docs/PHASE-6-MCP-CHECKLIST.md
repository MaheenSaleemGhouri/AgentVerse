# Phase 6 — MCP Ecosystem & Integrations: Completion Checklist

Requested as "Phase 7"; labelled Phase 6 to match `docs/roadmap.md`,
where Phase 7 is Billing. Same convention as ADR-0009.

## Deliverables

| # | Deliverable | Where |
| --- | --- | --- |
| 1 | Project structure | [mcp-integrations.md § Architecture](./systems/mcp-integrations.md) |
| 2 | MCP architecture | [ADR-0010](./adr/0010-mcp-integration-and-tool-execution-boundary.md) |
| 3 | Integration architecture | [mcp-integrations.md](./systems/mcp-integrations.md) |
| 4 | Database schema | Migration `c4e81f3d9b27`, 11 tables |
| 5 | API documentation | Generated OpenAPI (57 paths, 10 integration) + [§ API](./systems/mcp-integrations.md#api) |
| 6 | Marketplace documentation | [§ Why there are no per-service integrations](./systems/mcp-integrations.md) |
| 7 | Authentication flow | [mcp-flows.md § 1](./systems/mcp-flows.md) |
| 8 | Tool execution flow | [mcp-flows.md § 2](./systems/mcp-flows.md) |
| 9 | Runtime flow | [mcp-flows.md § 3](./systems/mcp-flows.md) |
| 10 | Security architecture | [Threat model](./security/threat-model-tool-execution.md) + [flows § 4](./systems/mcp-flows.md) |
| 11 | Testing report | Below |
| 12 | User guide | [connecting-integrations.md](./guides/connecting-integrations.md) |
| 13 | This checklist | — |

## Requested capabilities

### MCP platform

| Capability | Status | Note |
| --- | --- | --- |
| MCP Client | ✅ | The **SDK's** — `MCPServerStdio`/`Sse`/`StreamableHttp`. No protocol code written |
| MCP Registry | ✅ | `mcp_servers` catalog, 38 entries |
| Connection Manager | ✅ | `mcp/manager.py`, per-run lifecycle |
| Marketplace | ✅ | Browse, search, filter, install, enable/disable, remove |
| Permissions | ✅ | 3 levels × per-tool × agent/team/workspace |
| Authentication | ✅ | API key, bearer, basic, custom header, JWT; **OAuth2 partial — see below** |
| Health monitoring | ✅ | `check_health`, status per install |
| Logs | ✅ | `tool_calls` + `tool_logs`, both partitioned |
| Versioning | ✅ | `server_versions` + `diff_tool_surface` |
| Configuration | ✅ | Per-install non-secret config |
| Discovery | ✅ | Cached, with change detection |

### Supported servers — 38 catalog entries

18 official · 11 community · **9 `custom_required`**

All 38 services from the brief are present. The nine marked
`custom_required` — WhatsApp, Twilio, Salesforce, Microsoft Teams,
Outlook, Dropbox, OneDrive, Google Docs, Google Cloud — have **no
installable first-party MCP server today**. Their cards render with the
reason and a disabled Install button rather than a button leading to a
connection that can never succeed. A test asserts this field is not
uniformly optimistic.

### Tool execution

| Capability | Status |
| --- | --- |
| Retry, timeout, circuit breaker, caching, health checks | ✅ |
| Parallel calls | ✅ via the SDK's own concurrent tool dispatch |
| Sequential calls | ✅ |
| Execution history | ✅ every call, including refusals |
| Fallback tool | ⚠️ **Not built** — see gaps |
| Streaming results | ⚠️ **Not built** — see gaps |

### Frontend

| Screen | Route |
| --- | --- |
| Marketplace + Connected | `/integrations` |
| Server details (Tools · Credentials · Access · Activity) | `/integrations/{id}` |
| MCP runtime | `/mcp` |

Built from existing AVDS primitives. `feature-availability.ts` entries
for `mcp` and `integrations` **deleted** — a leftover pending panel now
fails the TypeScript build.

## Testing report

| Suite | Result |
| --- | --- |
| `packages/python-shared` | 267 passed |
| `apps/api` | 440 passed |
| `apps/worker` | 255 passed |
| `apps/web` | 33 passed |
| `promtool test rules` (alert unit tests) | SUCCESS |
| ruff + mypy (3 packages) | clean |
| tsc + eslint + next build | clean |

**995 tests, zero skipped.** The Python suites were re-run against a
real pgvector pg16 at revision `c4e81f3d9b27` with
`AGENTVERSE_{API,WORKER,SHARED}_DATABASE_URL` set, so the integration
layer — tenant isolation on `kb_chunks`, shared-memory and session
persistence, workspace/RBAC repositories — actually executed instead of
being deselected. Without those variables the same suites report 191 /
434 / 246 passing with 67 skips, which is the shape a CI run gives if it
forgets them: green, and missing exactly the coverage that matters most.

All four suites were re-run after the `cryptography` 46.0.7 → 48.0.1
bump, since that library seals every MCP credential.

**Security tests specifically:**

- **32 adversarial egress tests** — metadata IP direct and via DNS,
  `::ffff:169.254.169.254`, `2002:a00:1::`, IPv6 link-local/ULA,
  `file:`/`gopher:`/`dict:`, credentials-in-URL, mixed public/private
  resolution, redirect chains hopping to metadata, over-long chains
- **35 crypto tests** — tamper detection, AAD row-binding (ciphertext
  moved between workspaces fails), KEK rotation, no-fallback-key
- **35 boundary tests** — read-only refusing a mutating tool *before
  execution*, argument validation, untrusted wrapping, forged closing
  tag, breaker, per-tenant cache isolation, per-run budget
- **Route tests** — plaintext never in a response body, install refusal
  for `custom_required`, stdio rejected for custom servers,
  cross-workspace 404
- **Catalog tests** — every installable entry can connect; every
  unavailable one explains itself; no shell metacharacters in stdio args

Migration verified against real pg16: `upgrade → downgrade → upgrade`,
`relkind='p'` on both partitioned tables.

## Definition of Done

| # | Item | Status |
| --- | --- | --- |
| 1 | Requirements | ✅ brief + roadmap Phase 6 |
| 2 | Architecture | ✅ ADR-0010 |
| 3 | Security reviewed | ⚠️ [`security-reviewer` pass run](./security/phase-6-security-review.md) — no blocking finding, one dependency finding fixed (`cryptography`), `starlette` advisories accepted via the FastAPI pin. **`owasp-expert` standing audit still not run** |
| 4 | Tests passing | ✅ |
| 5 | Documentation | ✅ 8 documents |
| 6 | Performance | ⚠️ [Budgets published](./performance/tool-execution-budgets.md) — **no measurement, no load test, no CI gate**, so the item is not satisfied |
| 7 | Accessibility | ⚠️ [axe gate green, 2 real defects fixed](./accessibility/phase-6-audit.md) — **manual keyboard, screen-reader, contrast, reduced-motion passes not run** |
| 8 | Monitoring | ⚠️ [9 metrics emitted and scraped, 7 alert rules unit-tested, routing + 10-panel dashboard checked in, all gated in CI](./observability/tool-execution-monitoring.md) — **no PagerDuty/Slack receiver provisioned, so nothing pages a human yet** |
| 9 | Deployment ready | ✅ additive migration, reversible; KEK documented in both `.env.example` files and compose; **both `runtime` images now build and are gated by the `container-build` CI job** (they had been unbuildable since Phase 5 — shared package resolved by relative path, never copied into the image) |
| 10 | Final review | ⚠️ [Go-with-conditions recorded](./releases/phase-6-go-no-go.md) |

## Gaps — what is not built

Listed plainly rather than implied by omission.

1. **OAuth2 is scaffolded, not finished.** `oauth_sessions` exists with
   PKCE storage and single-use `DELETE … RETURNING` consumption; the
   repository methods and the state/expiry helpers are written and
   tested. **The authorize-redirect and token-exchange endpoints are
   not.** OAuth catalog entries (Notion, Linear, Jira, HubSpot,
   Cloudflare) install but cannot complete their flow. Servers using
   API keys or bearer tokens work end to end today.

2. **No fallback tool.** If a tool fails, the agent is told and adapts.
   Automatic substitution of a different tool is not implemented — it
   needs a notion of tool equivalence that does not exist yet.

3. **Streaming tool results.** Results are returned whole. MCP supports
   streaming; the boundary's size-cap and untrusted-wrapping logic
   assumes a complete string, and making it incremental is a real design
   change rather than a flag.

4. **Health monitoring is on-demand, not scheduled.** `check_health`
   works and runs on connect; there is no background sweep, so a server
   that dies between runs shows its last known state until something
   uses it.

5. **`tool_metrics` is written but never populated.** The table and its
   rollup target exist; the aggregation job does not. Metrics today are
   computed live from `tool_calls`, which is correct but will not scale
   to a large workspace's dashboard.

6. **No load or stress test.** The circuit breaker and budget are
   unit-tested for behaviour, not measured under concurrency.

7. **Partition rotation.** `tool_calls` and `tool_logs` have a single
   DEFAULT partition. Time-bounded partitions created ahead of need are
   an operational task, matching the existing `agent_run_steps` and
   `execution_events` position.

## Backward compatibility

Every prior phase is intact. `integrations` is an **optional** parameter
on `handle_agent_run_job` defaulting to `None`, so every pre-Phase-6
caller and test behaves exactly as before — no existing test needed
rewriting.

One deliberate change to an earlier phase: Phase 5's grounding and Phase
9's handoff renderer now use the shared `wrap_untrusted`. The threat
model commits to "one shared renderer, not a per-integration copy";
leaving three copies would have made that sentence false. All 20 handoff
tests still pass.

**New deployment requirement:** `AGENTVERSE_CREDENTIAL_KEK_V1` must be
set for both apps/api and apps/worker. Startup fails loudly without it —
that is the intended behaviour, not a bug.
