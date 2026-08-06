# Environment parity contract

What must be identical across `dev`, `staging` and `production`, and
what is deliberately allowed to differ.

The rule this document exists to enforce: **the three environments run
the same container images and the same config *shape*. Only values
differ.** There is no `if env == "production"` branch anywhere in
application code, and adding one is a review-blocking change — a code
path that only executes in production is a code path staging cannot
rehearse, which defeats the point of having staging.

Environment names are `dev`, `staging`, `production`. Never `stg`,
`prod` or `live`, in configs, logs or conversation.

## What must match

| Thing | Why it must match |
|---|---|
| Container image digest | `sha-<short-sha>`, built once and promoted. A rebuild per environment means production runs an artifact nothing tested. |
| Migration state (`alembic current`) | Staging is a rehearsal. A migration that has not run there has not been rehearsed. |
| Config *shape* — every variable in `.env.example` is set in every environment | A variable that exists only in production is a variable production is the first to test. |
| Feature-flag defaults | A flag that defaults differently makes staging exercise a different product. |
| `AGENTVERSE_<SERVICE>_<KEY>` naming | Drift becomes visible by diffing rather than by tribal knowledge. |

## What may legitimately differ

| Thing | dev | staging | production |
|---|---|---|---|
| Replica counts | 1 | 1–2 | scaled to load |
| `AGENTVERSE_API_LOG_LEVEL` | `DEBUG` | `INFO` | `INFO` |
| Data volume | fixtures | anonymised subset | real |
| External API keys | test keys | test keys | live keys |
| `external_labels.environment` in Prometheus | `local` | `staging` | `production` |

## Secrets, and the one that fails startup on purpose

Every secret lives in the environment or the secrets manager, never in
source, logs, error messages, client bundles or image layers (Rule 1).
There is no `os.environ.get("KEY", "changeme")` fallback anywhere in
this codebase; a missing required value fails startup loudly.

**Stripe is the one with an active guard.** `apps/api` refuses to start
when the key's mode contradicts the environment:

- `sk_test_` with `AGENTVERSE_API_ENVIRONMENT=production` → customers
  complete checkout and are never charged, while the product behaves as
  though they were.
- `sk_live_` anywhere else → a test run or a stray preview-environment
  webhook can move real money.

Both are silent until money is involved, which is why the check is at
startup rather than at first use. See
`Settings.validate_stripe_mode`.

`AGENTVERSE_API_STRIPE_SECRET_KEY` and
`AGENTVERSE_API_STRIPE_WEBHOOK_SECRET` are optional **as a pair**. An
environment with neither runs correctly — money-moving routes answer
`503` — which is the intended state for dev, CI and preview
environments. A secret key *without* a webhook secret counts as not
configured: it would take payments whose outcome the service could
never learn.

## Where each service runs

| Service | Platform | Rollback |
|---|---|---|
| `apps/web` | Vercel | Instant — promote the previous deployment |
| `apps/api` | Coolify/Railway/Docker | Redeploy the previous image tag |
| `apps/worker` | Coolify/Railway/Docker | Redeploy the previous image tag |
| Postgres | Managed | Restore from `infra/backup/` — see the DR section below |
| Redis | Managed | No restore. Rule 13: everything in it is reconstructable from Postgres or safely losable. |

## Residual risks staging cannot rehearse

Called out explicitly rather than discovered during an incident:

- **Live Stripe behaviour.** Staging uses test-mode keys, so
  live-mode-only behaviour (real card networks, real 3DS challenges,
  real webhook latency) is genuinely untested until production. The
  reconciliation sweep exists partly for this.
- **Production data volume.** Query plans that are fine against
  staging's row counts can change shape at production scale. Every
  billing query leads with `workspace_id` and has an index built for
  it, but "verified at realistic volume" is a claim staging cannot
  support.
- **Email deliverability.** No transactional email vendor is configured
  in any environment yet; the adapter logs what it would send. Nothing
  about delivery, bounces or spam placement has been exercised
  anywhere.

## Disaster recovery

| | |
|---|---|
| **RPO** (data loss tolerated) | 24h from the nightly dump, or the managed provider's PITR window where enabled — whichever is tighter. |
| **RTO** (time to restore) | ~30 min for a full `pg_restore` of a small database, dominated by the largest partitioned tables. |
| **Verification** | `infra/backup/verify.sh` takes a backup, restores it into a scratch database, and asserts the restored copy has rows — not just tables. Run on a schedule; an untested backup is a hypothesis. |

What backups deliberately do *not* cover, and why:

- **Redis** — cache, queue, rate-limit counters. Rule 13 already makes
  all of it reconstructable or losable.
- **Stripe** — the provider is the system of record for payment-method
  and invoice facts. Our tables are a projection, repaired by
  `ReconciliationService`, not by a restore.
- **Uploaded documents** — object storage, owned by its own lifecycle
  policy.
