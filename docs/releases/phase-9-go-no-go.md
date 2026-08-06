# Phase 9 — SaaS Platform, Billing & Production Readiness

**Go / no-go record.** Aggregates the milestone sign-offs, states what
shipped, and — more usefully — states what did *not*, so the gaps are a
decision on the record rather than something discovered later.

| | |
|---|---|
| Milestones | 8 (`v0.10.0-alpha.m1` … `m8`) |
| Commits | 16 |
| Verdict | **Go, with conditions** — the conditions are listed at the bottom and none of them block merge |

---

## What shipped

### The billing context (M1–M5)

A third bounded context in `apps/api`, layered like its siblings
(ADR-0012).

**Plans are data, not code.** The catalog lives in Postgres, seeded by
migration, validated on read. A price or limit change is an `UPDATE`,
not a deploy — which is what "configurable from the backend" has to mean
to be true. Unknown keys are a hard error, because `None` means
*unlimited* in this system and a typo'd key would silently grant every
workspace unlimited access.

**Subscriptions are a state machine with one write path.** Every
transition goes through a single method that checks idempotency, asks
the domain whether the transition is legal, then writes the status and
its event row together. There is no path that writes one without the
other.

Two modelling decisions carry most of the weight:

- *"Scheduled to cancel" is a flag, not a status.* A customer who
  cancels on day 3 has paid for the month. Making it a status would
  revoke entitlement immediately after taking their money.
- *`past_due` keeps full entitlement.* A failed charge is usually an
  expired card. Cutting service at the first failure converts a
  recoverable billing problem into churn; service stops when the bounded
  14-day window closes.

**Proration is exact and deterministic.** Integer cents over whole
seconds against real period boundaries, so a 28-day February and a
31-day March price differently and correctly. It reads no clock, so
recomputing from stored timestamps months later reproduces the same
cents — which is what makes an invoice line defensible in a dispute.
Rounding never favours the platform.

**Stripe sits behind a port.** Nothing above
`billing_service/infrastructure/stripe/` imports the SDK or knows a
`cus_` prefix exists. Money-moving actions call the provider *first*,
then this database — if that inverted, a failed provider call would
leave a customer marked canceled here and still charged there, with
nothing to detect it.

**Webhooks are claim → dispatch → resolve, in one transaction.** The
claim loses to a concurrent duplicate at a unique index, so a redelivery
is a no-op rather than a second dunning cycle. Dispatch contains no
state-machine logic of its own.

**Usage metering is partitioned from its first migration**, with a
DEFAULT catch-all — because an insert for an un-provisioned month being
*rejected* would be revenue nobody can reconstruct. Storage folds by
maximum, not sum: 5 GB held all month is 5 GB, not 150 GB-days.

**Quota is enforced before the work**, on the run-submission route,
before a single provider token is spent. Whether exceeding refuses or
bills is the plan's decision — which is what makes Free genuinely free.

**Credit is a ledger with a balance projection over it**, not a bare
number. "Why is this $40 and not $50" is the first question anyone asks
about credit, and a balance alone cannot answer it. Decrements take
`SELECT … FOR UPDATE`.

**Referrals qualify on first payment, never signup.** A signup-triggered
payout is a bounty on creating accounts, and it would be collected.

### The frontend (M6)

Billing dashboard and public pricing page, in AVDS. Every price and
limit reads the live catalog — the same rows quota enforcement reads —
so the price shown and the limit enforced cannot disagree. There is no
hardcoded price anywhere in the frontend.

Three states the UI is careful about: an unlimited dimension draws no
progress bar (a bar with no maximum has nothing truthful to render); an
unconfigured payment provider is distinguished from an empty invoice
list (the latter would read as "you have no invoices"); and a plan
change shows its exact proration before the confirm button.

### Notifications (M7)

A fourth bounded context. One rule shapes it: **a notification never
fails the thing that caused it.** A webhook that transitioned a
subscription and then could not send an email has still processed the
payment; a 5xx would make the provider retry a transition that already
succeeded.

Dedupe keys are derived from the event, never a timestamp — a sweep that
runs twice, a redelivered webhook and a retried job all produce one
message.

### Operations (M8)

Five billing metric families on a new `apps/api` `/internal/metrics`,
five alert rules with promtool unit tests, verified Postgres
backup/restore, a CI migration-reversibility gate, and the release and
rollback runbook set.

The alert selection criterion is worth restating: every rule covers a
failure that is **otherwise silent**. A failed customer payment is
deliberately not alerted — it already produces an email, an in-app
notification and a visible status.

---

## Verification

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | clean — api, worker, python-shared |
| `mypy src` | clean — 254 / 60 / 30 source files |
| `pytest` apps/api | **1142** passed |
| `pytest` apps/worker | **289** passed |
| `pytest` packages/python-shared | **257** passed, 10 skipped |
| `vitest` apps/web | **89** passed |
| Alert rules | 12 rules, `promtool check` + `test` green |
| Migrations | `upgrade → downgrade → upgrade` verified on real Postgres; full downgrade leaves 0 tables |
| Backup | verified end to end: 76 tables dumped, restored into a scratch database, 4 seeded plans present |
| `next build` | clean |
| OpenAPI | 92 → 117 paths across the phase; **0 paths, schemas or operations removed** at any milestone |

Backend tests grew 695 → 1142 (**+447**) across the phase. Web tests 72 →
89.

### Migrations added

| Revision | Adds |
|---|---|
| `f7d2c8b3a604` | `plans`, seeded with four tiers |
| `c5e9a1b7d380` | `billing_customers`, `billing_subscriptions`, `subscription_events` |
| `a3f81c6e5d72` | `billing_webhook_events` |
| `d94b7f2a1c68` | `billing_usage_events` (partitioned), `billing_usage_rollups` |
| `e61d5a83f907` | `billing_credits`, `billing_credit_transactions`, `billing_coupons`, `billing_coupon_redemptions`, `billing_referrals` |
| `f0a4c9e21b58` | `notifications`, `notification_deliveries` |

Every one is additive, and every `downgrade()` has been executed — not
merely written.

### Three pre-existing failures fixed on the way

All three were red before Phase 9 started, and are recorded here because
none was this phase's work — CI was not green on `main` when the phase
began:

1. **The apps/api CI job had been failing since the MCP OAuth2 work.**
   `api_public_url` became a required setting; `ci.yml` never got it,
   and `main.py` builds `Settings()` at import time, so `conftest.py`
   could not even be *collected*. The job was failing at pytest, not
   skipping.
2. **`next build` had been broken since `9a9d3a3`.** A client component
   imported a *value* from a module that transitively imports
   `server-only`.
3. **The `packages/python-shared` leg was failing `ruff format --check`.**
   Two files (`security/egress_guard.py`,
   `tests/observability/test_metrics.py`) had drifted; confirmed by
   checking out `v0.9.0-alpha` and re-running the check.

---

## Conditions on the "go"

None block merge. All are stated so they are decisions rather than
surprises.

**1. No payment provider is configured in any environment.** The Stripe
adapter is complete and tested against a fake, but no live or test key
exists anywhere. Checkout has never run against Stripe. Before taking
real money: create the Products/Prices tagged with `agentverse_plan` and
`agentverse_interval` metadata (the adapter resolves prices by that
metadata, and refuses loudly rather than falling back), set the key pair,
and run one end-to-end checkout in staging.

**2. No transactional email vendor is configured.** The adapter logs
what it would have sent. Every template is unit-tested for content, but
nothing about deliverability, bounces or spam placement has been
exercised anywhere. Dunning depends on the inbox — a customer never told
their card failed will be canceled without warning.

**3. Alertmanager has no receivers.** The 12 rules evaluate correctly and
are unit-tested, but `alertmanager.yml` routes to nothing: receivers need
real credentials, which do not belong in a checked-in file. Wiring them
to a pager is a deployment step.

**4. `/pricing` renders dynamically, not statically.** The root layout
fetches SSO providers per request, which opts every route out of static
generation (`/login` is affected identically). The catalog fetch is still
cached at 60s, so the database is hit at most once a minute — but the
CDN-cacheable render this page wants needs that layout fetch moved behind
its own boundary. Out of scope for a billing phase; recorded in the file.

**5. Query plans are verified at development scale, not production
scale.** Every billing query leads with `workspace_id` and has an index
built for the access pattern, and the high-volume table is partitioned
from day one. But "verified at realistic volume" is a claim staging's row
counts cannot support.

**6. The third tier's slug is `team`, not `business`.** The spec said
Business; `CLAUDE.md`'s fixed vocabulary says Team, and the existing
billing page and roadmap agree. The tier carries exactly the capability
set the spec listed. `display_name` is a plain column, so presenting it
as "Business" is one `UPDATE` — no migration, no code change.

---

## Sign-off

| Gate | Owner | Status |
|---|---|---|
| Architecture | `architecture-reviewer` | ADR-0012 records the billing-context placement, plan-catalog storage and money-unit decisions |
| Database | `database-architect` / `postgresql-expert` | Six migrations, all additive, all downgrades executed; partitioning from the first migration |
| Security | `security-reviewer` | No card data in any schema; webhook signatures verified over raw bytes; every route `workspace_id`-scoped from the authenticated identity; key-mode guard at startup |
| Billing correctness | `billing-expert` | Integer cents throughout; proration deterministic and clock-free; every transition validated and logged; reconciliation for both provider drift and credit drift |
| Accessibility | `accessibility-expert` | 17 axe-core tests on the billing surfaces, plus assertions for the two rules no scanner knows (unlimited draws no bar; a reached limit is announced in text, not colour) |
| Testing | `testing-architect` | +447 backend tests; database-level guarantees asserted against real Postgres, not fakes |
| Release | `devops-engineer` | Rollback documented per service; migration reversibility now a CI gate; backup verified by restore |

**Verdict: go, with the six conditions above recorded.**

Conditions 1–3 are the ones that matter for taking real money, and all
three are configuration rather than code.
