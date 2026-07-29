# Monitoring — MCP integrations and tool execution

`CLAUDE.md` §19 item 8: RED/USE metrics on a checked-in dashboard, every
paging alert with severity, routing, and a runbook. Owner:
`observability-engineer`; logging schema `logging-expert`; tracing
`opentelemetry-expert`.

This document defines the dashboard and alerts. The metrics below are
**emitted** by the worker and the rules are **checked in and
evaluating**; what is still missing is a pager on the other end. The
last section says exactly which parts are real.

| Artifact | Where |
| --- | --- |
| Metric definitions | `packages/python-shared/src/agentverse_shared/observability/metrics.py` |
| Scrape endpoint | worker `GET /internal/metrics` |
| Scrape config | `infra/observability/prometheus.yml` |
| Alert rules | `infra/observability/alerts.yml` |
| Alert-rule unit tests | `infra/observability/alerts.test.yml` |
| Alert routing | `infra/observability/alertmanager.yml` |
| Dashboard | `infra/observability/grafana-dashboard.json` |
| Local stack | `prometheus` service in `infra/docker-compose.yml` |
| CI gates | `container-build` and `alert-rules` jobs in `.github/workflows/ci.yml` |

## What makes this surface different

Most alerting assumes errors are bad. Here the most security-relevant
signal is a **refusal**, which is the system working correctly. A denied
call is not an error to page on; a *change* in the denial rate is worth
looking at, and a denial naming the egress guard is worth looking at
immediately regardless of rate.

So the panels below separate three things that a naive error-rate metric
would merge:

| | Meaning | Alertable |
| --- | --- | --- |
| **Failure** | The tool ran and broke, or timed out | Yes — reliability |
| **Refusal** | A control stopped it before it ran | Only on rate change |
| **Egress denial** | An outbound call tried to reach a private/metadata address | **Always** — one is a signal |

## Metrics

Emitted from the worker: the boundary
(`apps/worker/src/agentverse_worker/tools/`), the MCP connection
manager, and the credential repository. All names are prefixed
`agentverse_`.

| Metric | Type | Labels | Purpose |
| --- | --- | --- | --- |
| `agentverse_tool_calls_total` | counter | `status` | RED: rate + errors. `status` is the full enum incl. `denied`, `circuit_open`, `cached` |
| `agentverse_tool_call_duration_seconds` | histogram | — | RED: duration. Buckets to 120 s (the hard timeout) |
| `agentverse_tool_boundary_overhead_seconds` | histogram | — | Our latency, isolated from the third party's *and* from retry backoff — the split the budget doc insists on |
| `agentverse_tool_calls_denied_total` | counter | `reason` | Which control refused: `permission`, `invalid_arguments`, `budget_exceeded`, `circuit_open`, `egress` |
| `agentverse_egress_denied_total` | counter | `range` | `metadata`, `link_local`, `loopback`, `rfc1918`, `cgnat`, … |
| `agentverse_mcp_connect_total` | counter | `outcome` | `healthy` / `degraded` / `unreachable` at run start |
| `agentverse_mcp_connect_duration_seconds` | histogram | — | Attachment cost at run start |
| `agentverse_circuit_breaker_opened_total` | counter | — | Open *transitions*, not failures |
| `agentverse_credential_unseal_failures_total` | counter | — | Should be flat zero — a non-zero value means AAD mismatch or key rotation trouble |

### Two changes the implementation forced

The design above is not what this document originally specified.
Recorded rather than quietly amended, because both changes are the kind
that look like details and are not.

**No `workspace_id`, `installed_server_id`, or `tool_name` label.** The
original plan carried all three and noted `workspace_id` as "a
cardinality risk at scale, dropped to a bucketed label if it becomes a
cost problem". Writing it made that untenable. `workspace_id` grows
with the customer base; worse, **`tool_name` is attacker-influenced** —
a custom MCP server declares its own tool names, so a server
advertising ten thousand tools mints ten thousand series and takes down
our monitoring from a customer's config. Every label is now drawn from
a closed vocabulary declared in code, and any unexpected value collapses
to `other`, so the cardinality ceiling is enforced by the metrics module
rather than trusted from call sites.

Nothing is lost. Per-tenant, per-server, and per-tool attribution lives
in `tool_calls` — partitioned, workspace-scoped, and already served by
`GET /integrations/metrics`. Prometheus answers "is the fleet healthy,
is anything being refused"; the tenant-scoped API answers "which
workspace, which server, which tool". That is the correct division, and
it also means the scrape endpoint carries no tenant data at all.

**`mcp_server_health` and `circuit_breaker_open` are counters, not
per-server gauges.** Both were specified keyed by `installed_server_id`,
which is the same unbounded-label problem. `circuit_breaker_opened_total`
counts open *transitions* — a single dead server contributes one event,
not one per failed call — and "which server is currently open" is a
question the integrations API already answers per workspace.

## Dashboard

One board, `mcp-tool-execution`. Panels in the order an on-call engineer
reads them:

1. **Call rate by status** (stacked) — the shape of normal traffic.
2. **Failure rate** — `error + timeout` over total, excluding refusals.
3. **Boundary overhead p50/p95/p99** — ours.
4. **End-to-end duration p50/p95/p99, by server** — theirs.
5. **Denials by reason** — permission vs egress, separated.
6. **Egress denials by range** — expected to be empty.
7. **Server health matrix** — one row per install.
8. **Open circuit breakers** — currently-tripped servers.
9. **Top tools by call volume** and **by failure rate** — the second is
   where a bad tool schema shows up.
10. **Cache hit ratio** — a collapse here explains a latency rise.

## Alerts

| Alert | Condition | Severity | Routes to | Runbook |
| --- | --- | --- | --- | --- |
| **Egress denial** | `increase(egress_denied_total[5m]) > 0` | **P1 page** | security on-call | [§ Egress denial](#runbook--egress-denial) |
| Credential unseal failure | `increase(credential_unseal_failures_total[15m]) > 0` | P1 page | platform on-call | [§ Unseal failure](#runbook--credential-unseal-failure) |
| Tool failure rate | `> 25%` over 15m, excluding refusals, above a traffic floor | P2 ticket | platform on-call | [§ Failure rate](#runbook--elevated-failure-rate) |
| Boundary overhead breach | p95 `> 25ms` over 15m | P3 ticket | platform on-call | Our code got slower. Profile the boundary; the third party is not involved in this metric |
| Breakers opening repeatedly | `> 5` open transitions in 30m | P3 ticket | platform on-call | [§ Breaker](#runbook--breaker-stuck-open) |
| Denial-rate change | permission denials `> 3×` the same hour a week earlier | P3 ticket | platform on-call | Usually a permission change with a wider blast radius than intended, or an agent newly reading injected content |
| MCP attachment failing | `> 50%` unreachable over 30m | P3 ticket | platform on-call | Expected to be non-zero and mostly customer-side; sustained above half points at our egress policy or DNS |

The executable form is `infra/observability/alerts.yml`; the exact
thresholds and their reasoning live there as comments next to each
expression, so the two cannot drift into disagreeing about a number.

**Egress denial pages at a single event, and that is deliberate.** In
normal operation nobody's MCP server resolves to `169.254.169.254`. One
occurrence is either an attacker probing for cloud credentials via an
injected instruction, or a genuine misconfiguration — both worth waking
someone for, and the rate will be zero the rest of the time. If it turns
out to be noisy in practice, the correct response is to find out *why*
it is firing, not to raise the threshold.

## Runbooks

### Runbook — egress denial

1. `tool_calls` row: `denial_reason` names the blocked range;
   `workspace_id`, `agent_id`, `installed_server_id`, `arguments`.
2. **Nothing was reached** — the guard runs before connect and revalidates
   each redirect hop. This is a blocked attempt, not a breach.
3. Establish which: a customer pointing at their own private network (a
   misunderstanding — answer with the "must be publicly routable" section
   of the user guide), or a *public* server redirecting to a metadata
   address (hostile; disable the install, notify, keep the row).
4. Repeated attempts from one agent after reading a document: treat as
   prompt injection. Check what the agent read and which grants it holds.
5. Do not "fix" by relaxing the guard.

### Runbook — credential unseal failure

1. Expected steady state is zero.
2. Check whether `AGENTVERSE_CREDENTIAL_KEK_V1` differs between apps/api
   and apps/worker — the usual cause, and the one the `.env.example`
   comments warn about.
3. If it changed, restore the previous value. Rows are readable under the
   version they were sealed with; a rewrap sweep is the migration path,
   not a hard cutover.
4. If the key is right, the AAD did not match — the ciphertext is bound
   to `(workspace, server, key)`. A mismatch means a row was moved. Treat
   as a possible tampering event, not a bug.

### Runbook — elevated failure rate

1. Is it one server or many? One → theirs. Many → check whether the
   worker fleet is degraded before blaming customers.
2. Compare against `mcp_server_health` and the diffed tool surface: a
   server that renamed its tools produces failures that look like ours.
3. The breaker should already be limiting the blast radius. If it is not
   tripping, that is the finding.

### Runbook — breaker stuck open

1. Confirm the server is genuinely down before intervening.
2. Do not clear breaker state as a matter of routine; it re-arms itself.

**A limitation to know before you rely on this.** The alert fires on
repeated *open transitions*, not on a breaker that is stuck open. That
is a consequence of dropping `installed_server_id` as a label — see the
cardinality note above — and it means the original "open > 30m" check no
longer exists. A genuinely stuck-open breaker with a healthy server
would show as a run whose tools are unavailable and no alert at all.

Detecting it needs a scrape-time collector that reads breaker state out
of Redis, which is real work and is not done. Until it is, the
workspace-scoped integrations API is where a stuck breaker is visible,
and a customer reporting "my tools stopped working" is how you would
find out. Recorded because a gap named is a gap someone can close.

## Tracing and logs

Tracing is already in place from Phase 4 and unchanged: one trace per
run, with tool calls as child spans. Attachment emits
`mcp_server_attached` / `mcp_server_unavailable` trace events so a
degraded run explains itself without a log dive.

Logs follow the existing schema — `request_id`, `workspace_id`,
`run_id`. **Tool arguments and results are treated as customer PII by
default** (§10): the general log stream carries the tool name, status,
duration, and denial reason, never argument or result content. Content
lives only in `tool_calls`, size-capped, behind the workspace-scoped API.

## What is verified, and what is not

### Verified

- **The metrics are emitted.** The worker exposes them at
  `/internal/metrics`; asserted by 12 tests in
  `apps/worker/tests/tools/test_boundary_metrics.py` and 11 in
  `packages/python-shared/tests/observability/test_metrics.py`.
- **Prometheus scrapes them.** `docker compose up worker prometheus`
  brings the target up; confirmed against the live API —
  `http://worker:8001/internal/metrics health=up`, 24 distinct
  `agentverse_*` series in the TSDB.
- **All seven rules load and evaluate.** Confirmed via
  `/api/v1/rules`; all `inactive`, which is the correct steady state.
- **The rules fire when they should, and not when they should not.**
  `infra/observability/alerts.test.yml` is a `promtool test rules`
  suite covering a single egress denial paging, an old denial ageing
  out of the window, a credential unseal failure paging, and — the one
  that matters most — a flood of refusals *not* reading as an outage.
  Verified as non-vacuous by mutation: folding `denied` and
  `circuit_open` back into the failure-rate numerator makes that test
  fail, as it must.
- **No alert references a metric that is not emitted.** `promtool`
  cannot check this — a rule naming a metric that never exists parses,
  loads, and shows green while being unable to fire. A test in
  `apps/worker/tests/interface/test_metrics_route.py` cross-checks the
  rule file against the real exposition output.
- **Alertable series exist from process start.** Label children are
  pre-initialised at zero, so `increase(...) > 0` can distinguish "no
  denials" from "this process is not reporting". Without that, the two
  look identical on the one metric whose purpose is to be silent.

- **The dashboard is checked in and its queries are verified.** Ten
  panels in `grafana-dashboard.json`; the same test that guards the
  alert rules also cross-checks every panel query, because a panel on a
  metric nobody emits renders an empty graph that reads as "no traffic".
- **Routing is defined and validated.** `alertmanager.yml` routes p1
  security to a separate pager from p1 platform, and `amtool
  check-config` runs in CI. Receivers read credentials from mounted
  files, never inline (Rule 1).
- **CI enforces all of it.** The `alert-rules` job runs
  `promtool check` + `promtool test` + `amtool check-config`; the
  `container-build` job builds both `runtime` images, which is the gate
  that would have caught the Dockerfiles being unbuildable for two
  phases.

### Not verified

- **No pager is actually connected.** The routing exists; the secret
  files it reads do not exist in any environment yet, because no
  PagerDuty service or Slack webhook has been provisioned. Alertmanager
  will refuse to start without them, which is deliberate — an alerting
  stack that comes up unable to notify anyone is worse than one that
  fails loudly. **This is the one remaining gap on §19 item 8**, and it
  is a provisioning task, not a code task.
- **No alert has fired in anger.** Every rule is verified against
  synthetic series, never against a real incident.
- **The runbooks have never been exercised.**
- **A stuck-open circuit breaker is not detectable** — see the caveat
  in that runbook.
- **Retention, HA, and long-term storage** are managed-service
  concerns; the compose Prometheus is a local development stack with
  15-day local retention, not a model of production.

§19 item 8 asks for RED/USE metrics on a checked-in dashboard and every
paging alert to have severity, routing, and a runbook. All of that now
exists and is tested in CI. What is missing is a receiver on the other
end of the routing — real, and small, and someone's to provision.
