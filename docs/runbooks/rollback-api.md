# Rollback: apps/api

Template: symptom → diagnosis → mitigation → escalation.

## The action

```bash
# Redeploy the previous image tag. Never a fresh build under incident
# pressure — a build under pressure is a change nobody reviewed.
coolify deploy --service agentverse-api --image ghcr.io/agentverse/api:sha-<previous>
```

Tags are immutable and traceable to a commit (`sha-<short-sha>`), so
"the previous tag" is unambiguous. `latest` is never used for staging or
production precisely so this step cannot resolve to the wrong artifact.

## Before you roll back: does the schema allow it?

This is the question that decides whether a rollback is safe or is the
second incident.

Migrations in this repo are **additive and backward-compatible at deploy
time** (Rule 19), so the previous image can almost always run against
the current schema. Check the release log for what shipped:

| The release included | Rollback |
|---|---|
| No migration | Safe. Redeploy the previous tag. |
| An additive migration (new table, new nullable column) | Safe. The previous code ignores what it does not know about. |
| A migration with a `NOT NULL` column or a dropped column | **Stop.** The previous code cannot satisfy it. Roll the migration back first (`alembic downgrade -1`), then the image. |

Every migration in this repo has a tested `downgrade()` — verified
`upgrade → downgrade → upgrade` against real Postgres before merge, and
enforced in CI. That is what makes the third row an option rather than a
restore.

## Symptom → diagnosis

| Symptom | First check |
|---|---|
| `/ready` failing, `/health` fine | A hard dependency is unreachable: Postgres, Redis, or Better Auth's JWKS. The service is up and correctly refusing traffic. |
| 5xx across every route | Usually a config error at startup. Check whether the process is restart-looping — `Settings()` fails loudly on a missing required value, including the Stripe key-mode guard. |
| 502 on billing routes only | `ProviderError` — the payment provider, not us. Check `agentverse_payment_provider_calls_total{outcome="error"}`. |
| 503 on billing routes only | No payment provider configured in this environment. Expected in dev/CI/preview; a **misconfiguration** in production. |
| Webhooks failing | See `docs/runbooks/billing.md#webhook-processing-failure`. Do not roll back for this — the provider retries, and the rows are recorded. |

## What a rollback does not fix

- **Money already moved.** A charge taken by the payment provider is not
  undone by redeploying. Refunds are a deliberate, separately authorized
  action.
- **Webhooks already processed.** Their `billing_webhook_events` rows
  persist, and their idempotency keys mean re-processing after a
  rollback is a no-op — which is the intended behaviour, not a problem.
- **Credit already granted.** The ledger is append-only. A wrongly
  granted credit is corrected by a compensating ledger movement, never
  by editing a balance.

## Escalation

Schema questions → `database-architect`. Money questions →
`billing-expert`. Anything touching auth → `security-engineer`.
