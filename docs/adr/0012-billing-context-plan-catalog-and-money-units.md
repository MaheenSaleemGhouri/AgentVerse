# ADR-0012: Billing Bounded Context, Plan Catalog Storage, and Money Units

## Context

Phase 9 introduces subscriptions, Stripe, usage metering, invoicing, credits, and coupons. Every one of those milestones reads the same underlying facts: what plan is this workspace on, what does that plan allow, and what does exceeding it cost. Milestone 1 has to answer those three questions before anything else can be built on top, and three decisions in it are load-bearing for the whole phase — hard to reverse once M2–M5 depend on them.

**1. Where does billing live?** `apps/api` today has two bounded contexts, `auth_service` and `orchestration_service`, each layered `domain/ → application/ → infrastructure/ → interface/` per ADR-0001. Entitlement enforcement needs counts that those two contexts own: agents, teams, and knowledge bases (orchestration), workspace members and MCP installs (auth/orchestration). The tempting shortcut is to let billing `SELECT` from `agents`, `teams`, `knowledge_bases`, `installed_servers`, and `workspace_members` directly — it is one join away and there is no network boundary in the way. `CLAUDE.md` Rule 5 forbids exactly this ("no service reads another service's database directly"), and §5 makes each entity's owning context the only reader of its source-of-truth table.

**2. Where does the plan catalog live?** The spec requires plans to be "configurable from the backend." A Python constant in `domain/` is the least code; a `plans` table is more moving parts but makes a price or limit change an `UPDATE` rather than a deploy.

**3. What unit is money in?** Rule 15 is unconditional: money is integer cents, never floating point. But Phase 6 already introduced `agentverse_shared.cost_accounting` in **micro-USD** (1e-6 USD), because a single LLM call routinely costs a fraction of one cent and rounding each call to a cent would accumulate error over millions of calls. Two units now coexist, and something has to say which applies where. There is also a second-order problem: overage priced per single unit is not expressible in integer cents at all — "0.3¢ per agent run" has no integer-cent representation.

**4. Third tier naming.** The spec names the tiers Free/Pro/**Business**/Enterprise. `CLAUDE.md`'s fixed domain vocabulary says "subscription tier (Free/Pro/**Team**/Enterprise)", and the existing billing page and roadmap use Team.

## Decision

**Billing is a third bounded context, `billing_service`, and it reads other contexts only through their repositories.**

- New `apps/api/src/agentverse_api/billing_service/` with the same four layers as its two siblings.
- Every count billing needs is exposed as a method on the **owning** context's repository, not queried by billing: `SqlAgentRepository.count_for_workspace`, `SqlKnowledgeRepository.count_knowledge_bases`, `SqlTeamRepository.count_teams`, `SqlIntegrationRepository.count_installed`, `SqlWorkspaceRepository.count_members`. Each reuses that repository's existing live/soft-delete predicate, so billing can never disagree with the owning context about what "an agent" is.
- Billing's `SqlWorkspaceUsageRepository` composes those five calls behind one port. Billing owns exactly one table of its own in M1: `plans`.
- `EntitlementService.may_create` **re-measures** the count rather than trusting one supplied by the caller (Rule 6: enforcement is server-side, from authenticated state, never from client input).

**The plan catalog is a `plans` table, seeded by migration, validated on read.**

- Limits, allowances, capabilities, and overage rates are `jsonb` columns, validated by an application-layer Pydantic schema on **read** — the `agents.config` precedent in §8. Validation runs on read, not only on write, because a plan row gets edited operationally (a migration, an admin action, a support engineer at 2am) and the guarantee that must hold is "whatever is in the table parses", not "whatever we last wrote was fine".
- **Unknown keys are a hard error.** `None` means unlimited in this system, so a typo'd key (`"agent"` for `"agents"`) would deserialize happily and silently grant every workspace unlimited agents. `MalformedPlanError` maps to HTTP 500 and pages: it is an operator error in the catalog, never a caller's fault, and must never degrade into a permissive default.
- `PlanCatalogService.default_plan()` **raises `CatalogIncompleteError`** if the Free row is missing rather than falling back to hardcoded limits. A fallback would be a second, invisible copy of the pricing configuration — Rule 3.
- Tier slugs are `TEXT` + `CHECK`, not a Postgres `ENUM`. `ALTER TYPE ... DROP VALUE` does not exist, so an ENUM makes the migration irreversible, violating Rule 19. A `TypeDecorator` (`PlanTierType`) keeps the ORM attribute typed `Mapped[PlanTier]` over the TEXT column, so the type safety is not paid for.

**Money units are split by boundary, and overage is priced per increment.**

- **Integer cents** for everything customer-facing and stored on `plans`, subscriptions, and invoices (Rule 15).
- **Micro-USD** stays the unit for per-LLM-call cost accrual (`agentverse_shared.cost_accounting`, Phase 6), converted to cents exactly once, at the invoice-line boundary in M4. Two units, one conversion point, stated here so M4 does not invent a second.
- **Overage is `price_cents_per_increment` over a `billing_increment`** (e.g. 300 cents per 1,000 agent runs), never a per-unit price. This is what makes sub-cent rates expressible in integer cents at all, and `overage_units` rounds the final partial increment **up** — a customer who uses 1,001 runs over their allowance is billed two increments, which is the arithmetic every metered SaaS uses and the one a customer can verify by hand.
- `None` means unlimited, everywhere, and never a sentinel like `-1`. `overage_cents` returns 0 for a `None` allowance regardless of usage, asserted directly against the seeded Enterprise row.

**The third tier keeps the slug `team`.**

`CLAUDE.md`'s fixed vocabulary wins over the spec's wording (§18.6: conflicts are resolved by citing the owning standard), and the existing billing page and roadmap already say Team. The tier carries exactly the capability set the spec listed for "Business". `display_name` is a plain configurable column, so presenting it as "Business" is one `UPDATE` with no migration and no code change — the naming is a runtime decision, not one baked into the schema.

## Consequences

**Positive.** Billing never holds a query that could disagree with the context that owns the data, so a change to what counts as a live agent lands in one place. A price change is an `UPDATE` against `plans`, deployable without a release. The catalog's own consistency properties — each tier grants at least what the tier below grants, no tier lowers a resource limit, upgrading never raises a per-unit overage price, Free carries no overage rates at all — are asserted structurally against the seeded rows in integration tests, so a future pricing edit that makes an upgrade worse than the tier below it fails CI rather than reaching a customer's invoice.

**Negative.** Five repositories in two other contexts each grew a `count_*` method they did not previously need, and the entitlements endpoint issues five queries where one join would do. That cost is accepted: at one call per entitlements read it is not on a hot path, and the alternative trades a correctness boundary for a latency saving that has not been measured to matter. If it ever does, the fix is a cached projection owned by billing, not a cross-context join.

**Negative.** Storing plans in a table means a malformed row can break the pricing page and the entitlements endpoint at runtime, where a Python constant would have failed at import. This is why validation is strict, on read, and fails loudly rather than defaulting — the failure is made obvious rather than made impossible, because "impossible" here would mean giving up backend configurability, which the spec requires.

**Negative.** Two money units coexist in the codebase. Mitigated by confining micro-USD to per-call accrual and naming the single conversion point here, but it remains something a reader has to know.

## Alternatives considered

- **Billing joins the other contexts' tables directly.** Rejected: Rule 5, and it would duplicate each context's soft-delete/live predicate in billing, where it would drift.
- **Plans as a Python constant.** Rejected: "configurable from the backend" is an explicit requirement, and a constant makes every price experiment a deploy.
- **Plan limits as typed columns instead of `jsonb`.** Rejected: nine metered dimensions, six resource limits, and sixteen capabilities means every new dimension is a migration on a table with four rows. `jsonb` plus strict read-time validation gets the same safety without the migration churn — the tradeoff §8 already made for `agents.config`.
- **Per-unit overage price in cents.** Rejected: not expressible for any rate below one cent per unit, which is most of them.
- **Millicents or micro-USD stored on `plans`.** Rejected: Rule 15 is unconditional for customer-facing money, and a published price of $29.00 has no sub-cent component to preserve.
- **Extending `orchestration_service` with billing instead of a new context.** Rejected: billing has a genuinely independent lifecycle (Stripe webhooks, invoice periods, dunning) and a different failure-isolation need — §5's bar for a real boundary is met, unlike a split made for tidiness.
- **Renaming the tier to "Business" to match the spec.** Rejected as a *schema* change; available for free as a display change. Changing the slug would touch the CHECK constraint, the enum, the seeded row, and every test, to reach a state one `UPDATE` already reaches.
