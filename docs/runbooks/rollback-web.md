# Rollback: apps/web

## The action

Vercel deployments are atomic and immutable. Promote the previous one:

```bash
vercel rollback <previous-deployment-url> --scope agentverse
```

This is instant and needs no rebuild — the previous deployment's
artifacts are still stored.

## Before you roll back: does the API still serve it?

The frontend is generated against `packages/contracts`, which is
generated from `apps/api`'s OpenAPI schema. A frontend rollback is safe
whenever the API contract it was built against is still served.

Contract changes in this repo are **additive** — asserted per release by
diffing the OpenAPI export for removed paths, schemas and operations. So
an older frontend calling a newer API is fine: it simply does not use
the new fields.

The unsafe direction is the other one, which is why the deploy order is
migration → backend → frontend and the rollback order is its reverse.

## Symptom → diagnosis

| Symptom | First check |
|---|---|
| Build fails with `server-only` in a client component | A client component imported a *value* from `lib/api/*`. Those modules import `lib/api/client.ts`, which is `server-only`. Client code may import types (erased) and call server actions; a runtime value belongs elsewhere. |
| A page renders an `IntegrationPending` panel unexpectedly | Its `feature-availability.ts` entry was re-added, or the backend it names regressed. |
| Billing page shows "payments are not configured" | Expected where no Stripe credentials are set. In production it means the environment lost them. |
| Everything 500s after a deploy | Check `lib/env.ts` — it validates required variables at import time and fails loudly. |

## Escalation

Frontend architecture → `senior-frontend-engineer`. Contract shape →
`api-designer`.
