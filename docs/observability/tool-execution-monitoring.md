# Monitoring — MCP integrations and tool execution

`CLAUDE.md` §19 item 8: RED/USE metrics on a checked-in dashboard, every
paging alert with severity, routing, and a runbook. Owner:
`observability-engineer`; logging schema `logging-expert`; tracing
`opentelemetry-expert`.

This document defines the dashboard and alerts. **None of it is
deployed** — there is no metrics backend running. See the last section.

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

Emitted from the boundary (`apps/worker/src/agentverse_worker/tools/`),
labelled `workspace_id`, `installed_server_id`, `tool_name`, `status`.

`workspace_id` as a label is a cardinality risk at scale. It is kept
because per-tenant attribution is what makes these numbers actionable,
and dropped to a bucketed label if cardinality becomes a cost problem —
recorded here so that trade-off is a decision, not a surprise.

| Metric | Type | Purpose |
| --- | --- | --- |
| `tool_calls_total{status}` | counter | RED: rate + errors. `status` is the full enum incl. `denied`, `circuit_open`, `cached` |
| `tool_call_duration_seconds` | histogram | RED: duration. Buckets to 120 s (the hard timeout) |
| `tool_boundary_overhead_seconds` | histogram | Our latency, isolated from the third party's — the split the budget doc insists on |
| `tool_calls_denied_total{reason}` | counter | `reason` distinguishes a permission refusal from an egress denial |
| `egress_denied_total{range}` | counter | `range` = rfc1918 / loopback / link_local / metadata |
| `mcp_server_health{installed_server_id}` | gauge | 1 healthy, 0 unreachable |
| `mcp_connect_duration_seconds` | histogram | Attachment cost at run start |
| `circuit_breaker_open{installed_server_id}` | gauge | USE: saturation of a downstream |
| `credential_unseal_failures_total` | counter | Should be flat zero — a non-zero value means AAD mismatch or key rotation trouble |

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
| Tool failure rate | `> 25%` per server over 15m, min 20 calls | P2 ticket | platform on-call | [§ Failure rate](#runbook--elevated-failure-rate) |
| Boundary overhead breach | p95 `> 25ms` over 15m | P3 ticket | platform on-call | Our code got slower. Profile the boundary; the third party is not involved in this metric |
| Breaker stuck open | open `> 30m` | P3 ticket | platform on-call | [§ Breaker](#runbook--breaker-stuck-open) |
| Denial-rate change | permission denials `> 3×` the 7-day baseline | P3 ticket | platform on-call | Usually a permission change with a wider blast radius than intended, or an agent newly reading injected content |
| Server unreachable | health 0 `> 1h` with attach attempts | P3 ticket | platform on-call | Expected to be common and mostly customer-side |

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
2. A stuck-open breaker with a healthy server means the half-open probe
   is not running — a platform bug, and the reason this alert exists.
3. Do not clear breaker state as a matter of routine; it re-arms itself.

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

## Not deployed

Everything above is a specification. There is no metrics backend, no
dashboard, and no alert manager in this environment, so:

- No metric named here is currently emitted. Instrumenting the boundary
  to emit them is real work that has not been done.
- No alert can fire.
- The runbooks have never been exercised.

`CLAUDE.md` §19 item 8 is **not satisfied** by this document. It is the
design the instrumentation should implement, written now so the
instrumentation has a target — not evidence that monitoring exists.
