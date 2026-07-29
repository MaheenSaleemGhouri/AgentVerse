# Phase 6 — release decision

`CLAUDE.md` §19 item 10. The `final-qa-reviewer` role aggregates the
upstream gates; it does not re-review from scratch. Every line below
points at the gate that owns it, and where a gate is short, it says so
rather than rounding up.

Scope: MCP ecosystem, universal integrations platform, and the central
tool-execution boundary. Checklist: `PHASE-6-MCP-CHECKLIST.md`.

## Decision

**GO WITH CONDITIONS — staging only. Not cleared for production.**

*Revised after the monitoring instrumentation landed and after a
deployment defect was found. The verdict is unchanged; the reasons for
it are not.*

The code is complete and correct as far as the gates that ran can
establish. Monitoring and deployment are both closed as engineering
work: metrics are emitted and scraped, alert rules are unit-tested,
routing and a ten-panel dashboard are checked in, and CI now builds
both `runtime` images and validates the whole observability config.

**Two things hold production back.**

1. **No alert receiver is provisioned.** The routing exists and reads
   its credentials from mounted secret files; no PagerDuty service or
   Slack webhook has been created, so those files exist nowhere and
   Alertmanager cannot start. Until someone provisions them, an egress
   denial is a row in Prometheus that nobody is told about — and the
   security controls this phase is built around are only as good as the
   notice they generate.

2. **The manual accessibility passes.** Keyboard-only operation and a
   screen-reader run need a browser and a person; neither has happened,
   and §19 item 7 makes `accessibility-expert` the last gate before a
   UI surface ships.

   Contrast, which was the harder half, is closed: measuring found six
   real AA failures in the shared palette — `StatusBadge` text at
   2.14:1–3.29:1 against a 4.5:1 requirement, the default `Button` at
   4.35:1 — and they are fixed by splitting the text role
   (`--{status}-strong`) from the decorative hue rather than dulling
   every dot and border. 34 contrast assertions now run in CI across
   both themes. Worth noting for the record that the audit had
   previously *guessed* these tokens were "very likely already
   compliant"; they were not, and only measuring found it.

Recorded because it was found here rather than in an incident: **both
container images had never been built successfully.** `api.Dockerfile`
and `worker.Dockerfile` copied only their own service directory while
both `pyproject.toml` files resolve `agentverse-shared` by relative
path, so `uv sync` failed inside every image from Phase 5 onward. It
went unnoticed because every green pipeline and every local stack ran
the services with `uv run` on the host. Fixed, and CI now builds the
`runtime` target on every PR so it cannot recur — but "deployment
ready ✅" had been asserted for two phases with no deployable artifact,
and that is a gate that was not actually being checked.

## Gate roll-up

| Gate | Owner | Verdict |
| --- | --- | --- |
| 1 Requirements | `product-manager` | ✅ brief + roadmap Phase 6 |
| 2 Architecture | `architecture-reviewer` | ✅ ADR-0010 |
| 3 Security | `security-reviewer` | ✅ Pass + `owasp-expert` Top 10 audit; 2 findings fixed, no penetration test |
| 4 Tests | `testing-architect` | ✅ 995 tests green across four suites, zero skipped, plus the alert-rule unit suite; lint/type clean |
| 5 Documentation | `documentation-engineer` | ✅ |
| 6 Performance | `performance-engineer` | ⚠️ Tool path measured + CI-gated; endpoint/frontend budgets unmeasured |
| 7 Accessibility | `accessibility-expert` | ⚠️ Contrast measured, 6 failures fixed, CI-gated; manual keyboard + screen-reader passes not run |
| 8 Monitoring | `observability-engineer` | ⚠️ Instrumented, scraped, alert-tested, dashboard + routing checked in and CI-gated; **no receiver provisioned** |
| 9 Deployment | `deployment-engineer` | ✅ Additive migration with tested downgrade; both `runtime` images build and are CI-gated (**they had not built since Phase 5**) |
| 10 Final | `final-qa-reviewer` | This document |

## What ran, and what it proves

**Tests (gate 4).** 267 + 440 + 255 + 33 across shared, api, worker, and
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

1. **Staging deployment only, until an alert receiver exists.** The
   metrics condition is met. What remains is provisioning a PagerDuty
   service and a Slack webhook and mounting their credentials at
   `/etc/alertmanager/secrets/` — after which the two P1 rules reach a
   human and this condition lifts. This is the single item standing
   between the release and production.
2. **`AGENTVERSE_CREDENTIAL_KEK_V1` must be set for both apps/api and
   apps/worker, to the same value.** Startup fails loudly without it.
   Divergent values produce credentials one service cannot read — the
   failure mode the runbook covers first.
3. **OAuth2 catalog entries must stay unadvertised.** Notion, Linear,
   Jira, HubSpot, and Cloudflare install but cannot complete a flow; the
   authorize and token-exchange endpoints are not built. Marketing or
   docs claiming these work would be a false claim (`CLAUDE.md` §2,
   transparency).
4. ~~**CI must set `AGENTVERSE_{API,WORKER,SHARED}_DATABASE_URL`.**~~
   **Withdrawn — it already does.** This was raised after a local run
   skipped 67 tests without them, and stated as a condition without
   checking the pipeline. `.github/workflows/ci.yml` gives every matrix
   leg its own pgvector service, sets all three variables, and applies
   the migrations first. The concern was real; the condition was not.
   Left visible rather than deleted, because a withdrawn finding is
   part of the record.
5. **A load test before any workspace exceeds roughly 100k tool calls.**
   The metrics endpoint aggregates live over `tool_calls`; the
   `tool_metrics` rollup job does not exist.
6. **Existing local stacks need no manual cleanup, but the venv volumes
   were renamed.** The service directories moved inside the images from
   `/app` to `/src/apps/<service>`, and a venv records absolute paths.
   `api_venv`/`worker_venv` became `api_venv_src`/`worker_venv_src` so
   the next `docker compose up` creates fresh ones instead of failing
   with `Failed to spawn: uvicorn`. The old volumes are orphaned, not
   deleted; `docker volume prune` reclaims them when the developer
   chooses.

## Rollback

**Read this first: there is no previous image tag.** The Dockerfile
defect above means no prior Phase 5 or Phase 6 image was ever built
successfully, so "redeploy the previous tag" has nothing to redeploy.
The first successful build of this service is the one in this change.
Once a staging deploy produces a tagged image, the rollback story below
becomes real; until then, rollback means reverting the commit and
building again, which is exactly the fresh-build-under-pressure that a
rollback plan exists to avoid.

Thereafter: one action, redeploy the previous image tag. Migration
`c4e81f3d9b27` is
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
