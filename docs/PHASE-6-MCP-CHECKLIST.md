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
| Authentication | ✅ | API key, bearer, basic, custom header, JWT, OAuth2 (full PKCE flow) |
| Health monitoring | ✅ | `check_health` on-connect, plus a scheduled background sweep |
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

**995 tests, zero skipped**, at the time this checklist was first
written. Closing gaps 1/4/5/6 (above) since added: 12 OAuth flow tests,
6 health-sweep tests, 7 tool-metrics tests (3 pure-logic + 4 real-SQL
integration), and 1 real-Redis circuit-breaker concurrency test to
`apps/worker` and `apps/api` — re-run and passing, exact combined totals
not re-snapshotted here since the api/web suites are otherwise
unchanged from the count below. The Python suites were re-run against a
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
| 3 | Security reviewed | ✅ [`security-reviewer` pass](./security/phase-6-security-review.md) + [`owasp-expert` Top 10 audit](./security/owasp-audit-phase-6.md) — no blocking finding; 2 findings fixed (`cryptography` CVE, KEK in `.env.example`), `starlette` accepted with an owner. **No penetration test** |
| 4 | Tests passing | ✅ |
| 5 | Documentation | ✅ 8 documents |
| 6 | Performance | ⚠️ [Budgets published; tool path measured under concurrency and CI-gated](./performance/tool-execution-budgets.md) — overhead is 4.5 Redis round trips, refusals 0.60× a permitted call. **Endpoint and frontend budgets still unmeasured; no Lighthouse/bundle gate** |
| 7 | Accessibility | ⚠️ [axe gate green, 2 defects fixed, contrast measured and **fixed**](./accessibility/phase-6-audit.md) — 6 AA failures found in the shared palette and closed by splitting `--{status}-strong` from the decorative hue; 34 contrast assertions CI-gated in both themes. **Manual keyboard + screen-reader passes still not run** |
| 8 | Monitoring | ⚠️ [9 metrics emitted and scraped, 7 alert rules unit-tested, routing + 10-panel dashboard checked in, all gated in CI](./observability/tool-execution-monitoring.md) — **no PagerDuty/Slack receiver provisioned, so nothing pages a human yet** |
| 9 | Deployment ready | ✅ additive migration, reversible; KEK documented in both `.env.example` files and compose; **both `runtime` images now build and are gated by the `container-build` CI job** (they had been unbuildable since Phase 5 — shared package resolved by relative path, never copied into the image) |
| 10 | Final review | ⚠️ [Go-with-conditions recorded](./releases/phase-6-go-no-go.md) |

## Gaps — what is not built

Listed plainly rather than implied by omission. Four of the original
seven have since been closed (below); the remaining three are
documented as still open, not silently dropped.

1. ~~OAuth2 is scaffolded, not finished.~~ **Closed.** `OAuthFlowService`
   (`orchestration_service/application/oauth_flow.py`) implements the
   full PKCE authorization-code flow — `start()` builds the
   authorize-redirect with a per-attempt `code_verifier`/`state` sealed
   into `oauth_sessions`, and the new public
   `GET /api/v1/integrations/oauth/callback`
   (`interface/routers/oauth_callback.py`) exchanges the code, seals the
   access/refresh tokens through the same `CredentialVault` as every
   other auth scheme, and redirects into the workspace's integration
   detail page. `OAuthProviderConfig` (a registry keyed by catalog slug,
   `infrastructure/oauth/providers.py`) exposes only providers whose
   client id/secret are actually configured — Notion, Linear, Jira,
   HubSpot, and Cloudflare now install and complete their flow
   end-to-end; 12 tests in `test_oauth_flow.py`, all passing.

2. ~~No fallback tool.~~ **Closed.** `ToolGrant.fallback_tools`
   (migration `45501a9a09d6`) is an admin-configured `{tool: fallback}`
   map, same server only. `execute_tool` tries it once, only after a
   genuine failure (not a denial, not against a just-opened breaker),
   through the same permission/schema/budget/cache checks. Tested: 7
   unit tests, 2 `GovernedMcpServer` tests, 1 real-Postgres test.

3. **Streaming tool results.** Still open, for the same reason: the
   boundary's size-cap and untrusted-wrapping logic
   (`sanitize_result`/`wrap_untrusted`) assumes a complete string, and
   making it incremental changes that contract, not just this feature.
   Not started.

4. ~~Health monitoring is on-demand, not scheduled.~~ **Closed.**
   `HealthSweeper` (`apps/worker/src/agentverse_worker/mcp/health_sweep.py`)
   runs as a third background task in the worker's lifespan, sweeping
   every active installation on a configurable interval
   (`mcp_health_sweep_interval_seconds`, default 300s) with bounded
   concurrency and a Redis `DistributedLock` so N worker replicas
   produce one sweep, not N. 6 tests, all passing.

5. ~~`tool_metrics` is written but never populated.~~ **Closed.**
   `ToolMetricsAggregator` (`apps/worker/src/agentverse_worker/mcp/metrics_aggregation.py`)
   runs as a fourth background task, re-aggregating the last 2 trailing
   hourly buckets every `tool_metrics_aggregation_interval_seconds`
   (default 900s) via a Postgres `ON CONFLICT` upsert keyed to
   `uq_tool_metric_bucket`, coordinated the same way as the health
   sweep. Verified against real Postgres: upsert-not-duplicate on
   re-aggregation, `[start, end)` bucket-boundary exclusion, and
   `percentile_cont` p95 — 4 integration tests plus 3 pure-logic
   scheduling tests, all passing. **`/runtime/metrics` still reads live
   from `tool_calls`, deliberately** — cutting the read path over to the
   rollup is a separate, dedicated change (see the module's own
   docstring), not bundled into populating the table.

6. ~~No load or stress test.~~ **Closed.**
   `test_boundary_load.py::TestCircuitBreakerConcurrency` fires 20
   concurrent failures against the same dying server and confirms the
   breaker opens exactly once despite the race (no double-count on the
   `SET … get=True` transition), then fires a second 20-call wave after
   the breaker is confirmed open and confirms it is fully blocked —
   zero further calls reach the dead server, not just fewer of them.
   Runs against real Redis, marked `integration`.

7. **Partition rotation.** Still open. `tool_calls` and `tool_logs` have
   a single DEFAULT partition. Time-bounded partitions created ahead of
   need are an operational task spanning `agent_run_steps` and
   `execution_events` too, not unique to Phase 6 — treated as
   cross-cutting and out of this checklist's scope rather than fixed
   inconsistently for two tables out of four.

**Still not actionable by an engineering change alone:** the DoD item 8
gap (no PagerDuty/Slack receiver — needs account provisioning) and the
DoD item 7 gap (manual keyboard/screen-reader pass — needs a human in a
browser) remain open for those reasons.

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
