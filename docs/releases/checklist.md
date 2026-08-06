# Release readiness checklist

Process scales with risk, not with ceremony. A copy change and a billing
migration do not go through the same gate, and pretending otherwise
means one of them gets the wrong amount of attention.

Classify the change first, then apply the matching column.

## Risk classification

| Tier | What it covers | Examples from this repo |
|---|---|---|
| **Low** | No schema change, no auth/billing logic, no infra | Frontend copy, a new read-only endpoint, a docs update |
| **Medium** | New behaviour or a dependency change, still additive | A new dependency (`stripe`), a new route, a config default |
| **High** | Schema, money, identity, or infrastructure | Every Phase 9 milestone. Migrations, quota enforcement, the payment provider, RBAC |

If you are unsure which tier applies, it is the higher one.

## The gates

| Gate | Low | Medium | High |
|---|:-:|:-:|:-:|
| CI green (lint, type-check, tests, container build, dependency audit) | ● | ● | ● |
| Rollback path defined **before** shipping | ● | ● | ● |
| Recorded in the release log | ● | ● | ● |
| `code-reviewer` review | ● | ● | ● |
| OpenAPI + `packages/contracts` regenerated, diff reviewed as additive | — | ● | ● |
| Migration `upgrade → downgrade → upgrade` verified against real Postgres | — | — | ● |
| `database-architect` / `postgresql-expert` sign-off on migration safety | — | — | ● |
| `security-reviewer` sign-off (auth, billing, permissions) | — | — | ● |
| Staging smoke test: auth → agent run → billing event | — | — | ● |
| `architecture-reviewer` sign-off + ADR (new service, datastore, cross-service dependency) | — | — | ● |
| Accessibility verified (WCAG 2.2 AA) for any UI surface | ● | ● | ● |

Accessibility is on every row deliberately. It is a merge gate, not a
release gate — a UI change at any risk tier ships with it or does not
ship (Rule 7).

## Deploy sequencing

For a change spanning schema, backend and frontend, the order is fixed:

1. **Migration** — additive and backward-compatible, so the currently
   deployed code still works against the new schema.
2. **Backend** — now reads and writes the new shape.
3. **Frontend** — now depends on the new backend.

There must be no window in which an old client meets a new schema or a
new client meets an old backend. Destructive schema changes (column
drops, renames) ship as a **separate, later** migration, after the old
code path is fully retired — otherwise a rollback breaks the code that
is still deployed.

## Post-deploy verification

A release is not complete when the deploy finishes. It is complete when:

- `/health` and `/ready` are green on every service.
- Error rate and p95 latency are within baseline on the dashboards.
- For billing changes specifically: `agentverse_billing_webhooks_total`
  is still processing (not only deduplicating), and
  `agentverse_billing_credit_drift_total` has not moved. Both are
  otherwise-silent failures — see `docs/runbooks/billing.md`.

## Rollback

Every release has its rollback action defined before it ships. At
minimum: **redeploy the previous image tag** — never a fresh build under
incident pressure, because a build under pressure is a change nobody
reviewed.

Per-service procedures: `docs/runbooks/rollback-web.md`,
`docs/runbooks/rollback-api.md`, `docs/runbooks/rollback-worker.md`.

## Recording the release

Every release, successful or rolled back, is recorded. Silence is not a
signal, and a post-incident timeline that cannot reconstruct what
shipped when is the reason this line exists.
