# Phase 6 — release decision

`CLAUDE.md` §19 item 10. The `final-qa-reviewer` role aggregates the
upstream gates; it does not re-review from scratch. Every line below
points at the gate that owns it, and where a gate is short, it says so
rather than rounding up.

Scope: MCP ecosystem, universal integrations platform, and the central
tool-execution boundary. Checklist: `PHASE-6-MCP-CHECKLIST.md`.

## Decision

**GO WITH CONDITIONS — staging only. Not cleared for production.**

The code is complete and correct as far as the gates that ran can
establish. Three gates ran only in their automatable half, and one of
those (monitoring) is the reason production is excluded: shipping an
agent tool-execution surface with no metric emitted and no alert armed
means an egress denial or a credential unseal failure would be invisible
until someone looked at a database table.

## Gate roll-up

| Gate | Owner | Verdict |
| --- | --- | --- |
| 1 Requirements | `product-manager` | ✅ brief + roadmap Phase 6 |
| 2 Architecture | `architecture-reviewer` | ✅ ADR-0010 |
| 3 Security | `security-reviewer` | ⚠️ Pass, no blocking finding; `owasp-expert` audit not run |
| 4 Tests | `testing-architect` | ✅ 971 tests green across four suites, zero skipped; lint/type clean |
| 5 Documentation | `documentation-engineer` | ✅ |
| 6 Performance | `performance-engineer` | ❌ Budgets only — nothing measured |
| 7 Accessibility | `accessibility-expert` | ⚠️ Automated gate green; manual passes not run |
| 8 Monitoring | `observability-engineer` | ❌ Specified, not instrumented |
| 9 Deployment | `deployment-engineer` | ✅ additive migration with tested downgrade |
| 10 Final | `final-qa-reviewer` | This document |

## What ran, and what it proves

**Tests (gate 4).** 256 + 440 + 242 + 33 across shared, api, worker, and
web, with the database-backed integration layer actually running rather
than deselected. Migration verified on real pg16 through `upgrade →
downgrade → upgrade`, not a mocked database. 32 adversarial egress tests, 35 crypto
tests including AAD row-binding, 35 boundary tests including a
read-only grant refusing a mutating tool before execution. This is the
strongest gate in the set and it is genuinely green.

**Security (gate 3).** Tenant isolation, secrets handling, injection,
egress control, and execution bounds were reviewed by reading and hold.
One real dependency vulnerability (`cryptography`, the library sealing
every MCP credential) was found and fixed, not noted. `starlette`'s
advisories are transitive through the FastAPI pin and are accepted with
a named owner. Details and the accepted risk: `phase-6-security-review.md`.

**Accessibility (gate 7).** The scan found a critical
`aria-valid-attr-value` violation on both new screens — filter strips
built from `Tabs` emitting `aria-controls` that pointed at nothing. It
was fixed by giving the controls honest markup, not by suppressing the
rule, and the scan is now a permanent CI gate. A keyboard-unreachable
tooltip guarding credential requirements was also fixed.

## Conditions on this GO

1. **Staging deployment only.** Production requires gate 8 — at minimum
   `egress_denied_total`, `credential_unseal_failures_total`, and
   `tool_calls_total{status}` emitted, with the two P1 alerts armed.
   Without them the security controls work but nobody would know when
   they fire.
2. **`AGENTVERSE_CREDENTIAL_KEK_V1` must be set for both apps/api and
   apps/worker, to the same value.** Startup fails loudly without it.
   Divergent values produce credentials one service cannot read — the
   failure mode the runbook covers first.
3. **OAuth2 catalog entries must stay unadvertised.** Notion, Linear,
   Jira, HubSpot, and Cloudflare install but cannot complete a flow; the
   authorize and token-exchange endpoints are not built. Marketing or
   docs claiming these work would be a false claim (`CLAUDE.md` §2,
   transparency).
4. **CI must set `AGENTVERSE_{API,WORKER,SHARED}_DATABASE_URL`.** Without
   them the Python suites skip 67 tests and still report green — and the
   skipped set is precisely the tenant-isolation and persistence
   coverage. A pipeline that omits them is not testing the thing this
   release is riskiest about.
5. **A load test before any workspace exceeds roughly 100k tool calls.**
   The metrics endpoint aggregates live over `tool_calls`; the
   `tool_metrics` rollup job does not exist.

## Rollback

One action: redeploy the previous image tag. Migration `c4e81f3d9b27` is
additive — 11 new tables, no column dropped or renamed, no existing
table altered destructively — so previous-version code runs unchanged
against the new schema. The `downgrade()` is tested and reversible, but
it is not needed for a rollback and should not be run as part of one.

`integrations` is an optional parameter on `handle_agent_run_job`
defaulting to `None`, so a rolled-back worker processes queued jobs
exactly as it did pre-Phase-6.

## Release notes

User-facing notes are `technical-writer`'s and are not yet written. They
must state the OAuth2 limitation and the nine `custom_required`
services, because a release note that lists 38 integrations without that
qualification would be inaccurate.

## For the incident record

If Phase 6 causes an incident, the two most likely candidates are named
in advance so the retrospective starts with a hypothesis rather than a
search:

- **A third-party MCP server behaving badly under load.** The circuit
  breaker is unit-tested and never measured under concurrency.
- **A KEK mismatch between services after a deploy.** The single sharp
  edge in the deployment story, mitigated only by documentation and a
  loud startup failure.

Recorded by `final-qa-reviewer`. Superseded only by a later decision
document, never edited in place.
