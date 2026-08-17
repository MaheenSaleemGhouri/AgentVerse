# ADR-0015: Phase 11 — Anthropic as a Second Provider, the Referral↔Marketplace Loop, and Dogfooded Support Triage

## Context

`docs/roadmap.md`'s Phase 11 calls for four things: referral/template-sharing growth loops, a second LLM provider behind the existing abstraction, third-party marketplace publishing, and a dogfooded internal support-triage automation. An audit before implementation found the real codebase differs from the roadmap's assumptions in ways that change scope, and each finding forces a real decision recorded here.

**Finding 1 — `ProviderAdapter` is not on the real agent-run path.** `apps/worker`'s `agent_run_job.py` dispatches every run through the OpenAI Agents SDK's own `Agent`/`Runner`, never through `ProviderAdapter` (`orchestration_service/domain/ports/provider_adapter.py`). `ProviderAdapter` is consumed only by an internal API-key-test route and the docs assistant. A literal "add `anthropic_adapter.py`" would satisfy the port but not make Anthropic usable by a real customer agent run — the roadmap's own risk section names this exact failure mode ("if adding the Anthropic adapter turns out to require touching orchestration/business logic... escalate, not quietly patch around") and it applies in reverse: the adapter alone is not enough.

**Finding 2 — the referral system already exists but has never worked.** `billing_service/domain/referral.py`, `CreditService`, and migration `e61d5a83f907` (`billing_referrals`, `billing_credits`) are complete and tested — but `CreditService.attribute()`, meant to be called when a referred workspace signs up, had zero production call sites. `create_workspace` accepted no referral code at all. The referral loop was schema and domain logic with no trigger.

**Finding 3 — third-party marketplace publishing already shipped.** `marketplace_service`'s `ListingStatus` (DRAFT→PENDING_REVIEW→PUBLISHED/REJECTED→UNLISTED) and moderation routes were built in an earlier phase under a different label. Nothing in this ADR builds it again.

**Finding 4 — no DAG workflow engine exists.** Roadmap Phase 10 (DAG workflows) was never implemented, despite Phase 11's own technical-tasks section assuming it as a dependency for the support-triage agent. The dogfooding work cannot wait on it.

## Decision

### Anthropic is wired at the model-resolution boundary, not through `ProviderAdapter`, for real runs

`apps/worker`'s `agents/model_resolution.py` adds `resolve_model(model: str, *, anthropic_api_key) -> str | Model`: a model string with no `/` is OpenAI, resolved exactly as before (zero migration — every existing stored `agent_versions.config->>'model'` already looks like this); an `anthropic/`-prefixed string resolves to `agents.extensions.models.litellm_model.LitellmModel`, already vendored in the pinned `openai-agents==0.18.3` and enabled by adding the `litellm` package via the `[litellm]` extra (no SDK version bump). This is a one-line change at the `Agent(model=...)` construction site in `agent_run_job.py` — the reasoning loop, tool-use, guardrails, and tracing are untouched, satisfying the roadmap's "zero orchestration rewrite" requirement literally rather than by claiming a port satisfies it.

`ProviderAdapter` still gets a real `AnthropicProviderAdapter` (`orchestration_service/infrastructure/providers/anthropic_adapter.py`), mirroring `openai_adapter.py`'s retry/error-translation shape, for its two actual consumers (the provider-test route, the docs assistant) via a new `MultiProviderAdapter` that dispatches on the same model-prefix convention. This keeps the port's own promise ("a second provider implements the same four methods with zero changes required in any caller") literally true for both of its callers, without pretending it is also the customer-run path.

Anthropic's Messages API has no `response_format: json_schema` mode; `AnthropicProviderAdapter.structured_output` forces a single synthetic tool call (`tool_choice={"type": "tool", ...}`) and reads the already-parsed `input` back — the closest native equivalent CLAUDE.md §9 asks for.

### The referral gap is fixed, not re-designed; marketplace sharing reuses it rather than duplicating it

`CreditService.attribute()` is wired into `create_workspace` via a new optional `referral_code` field, resolved server-side through a new `billing_referral_codes` reverse-index table (`referral_code()` is a one-way hash with nothing to reverse — this table exists solely so a pasted-in code can resolve back to `referrer_workspace_id`, populated lazily and idempotently). An unknown, garbage, or self-referential code is a **silent no-op** — workspace creation must never fail over a string a stranger typed in.

Marketplace sharing reuses this same workspace-level `referral_code()` rather than inventing a listing-level share token: the value being measured ("did this workspace's presence in the marketplace bring in a new workspace") is exactly what the referral system already measures, and a second token concept would duplicate a mechanism Rule 3 forbids duplicating. A new `POST .../marketplace/listings/{slug}/share` route logs `marketplace.share_created` into the existing `audit_logs` table (no new event table), and a new `GET .../growth/metrics` route composes `AuditService`, `CreditService`, and `MarketplaceService` — three contexts' own services, never a cross-context table read (Rule 5) — into the counts the Analytics page's new Growth section renders.

### `support_service` is a new bounded context that calls `run_agent`, not a second execution system

A support ticket has its own lifecycle a human reviews after the triage run completes (`triaging → triaged/failed → resolved`) — state `agent_runs` has no concept of and should not grow for one internal-tool consumer. `support_service` is deliberately minimal: one table (`support_tickets`, `TEXT + CHECK` status, matching this repo's standing ENUM-avoidance per `f7d2c8b3a604`), one application service, three routes. Creating a ticket calls `orchestration_service.application.run_agent` in-process — the same use case `POST /agents/{id}/runs` calls over HTTP — reusing its idempotency-key handling, quota interaction, and job-queue enqueue verbatim rather than reinventing execution (CLAUDE.md §16: "Do NOT build a separate hardcoded AI system"). Reading a ticket resolves its triage result by reading that same run's `agent_run_steps` back and parsing the seeded `support-triage` template's own labelled-line output format (`category:`/`severity:`/`confidence:`/`draft_reply:`) — never asserted against exact LLM text, only against the label shape.

No DAG workflow is used (Finding 4): a single agent with an empty tool list is topology-appropriate for ticket classification, and the seeded `support-triage` template's `AgentTemplate` entry passes no `tools=` argument, so the installed agent structurally cannot take a side-effecting action — CLAUDE.md §4's "sensitive actions require human approval" holds by construction, verified against the runtime template, not assumed.

The dogfooding workspace itself is an ordinary workspace created through the normal `create_workspace` route with real members and RBAC — not the marketplace's `PLATFORM_WORKSPACE_ID`, which has no members by design and cannot be logged into. Documented as a runbook (`docs/systems/support-triage-dogfooding.md`), not a migration or seed script: fabricating the workspace with elevated privilege would mean the internal team is not exercising the same path a customer does, defeating dogfooding's point.

## Consequences

- A deployment with no `ANTHROPIC_API_KEY` configured behaves exactly as before this phase — `anthropic_configured` is `False`, `MultiProviderAdapter` never constructs the Anthropic branch, and no agent version can be created pointing at an `anthropic/`-prefixed model that would actually resolve (the model string itself is unvalidated free text either way, unchanged from before this phase).
- `packages/python-shared/cost_accounting.py` gained a fix alongside the new Anthropic entries: `gpt-4.1`/`gpt-4.1-mini` were already selectable in the agent-builder UI with no pricing entry, so every run against them raised `UnknownModelPricingError`. This was a pre-existing bug, closed in the same change that touched the table for Anthropic, not left in place.
- `billing_referral_codes` is a new table with no downgrade data-loss risk beyond itself (nothing else references it); its `downgrade()` drops it cleanly.
- `support_tickets.triage_run_id` is a cross-context foreign key into `orchestration_service`'s `agent_runs` — accepted under the same "one Postgres instance, worker-fleet-adjacent" exception `apps/worker`'s own config docstring already invokes, not a new precedent.

## Alternatives considered and rejected

- **Route real agent runs through `ProviderAdapter` to make it the literal single boundary.** Would require re-implementing streaming, tool-calling, and tracing that the OpenAI Agents SDK already does, on top of an SDK that already has a well-tested multi-provider extension — the exact "leak-driven rewrite" the roadmap's own risk section warns against, for no behavioral gain over the model-resolution approach.
- **Force `model_routing.py`'s dead `ROUTING_TABLE` scaffold into use as part of adding Anthropic.** Explicitly out of scope per its own docstring ("wiring this up before Phase 9 would be out of this phase's scope") — Anthropic support does not require a routing decision to exist yet.
- **A listing-level share token, separate from the workspace referral code.** Rejected as Rule 3 duplication of a mechanism that already measures the thing being asked for.
- **Fold `support_tickets` into `orchestration_service`.** Rejected: blurs "control plane for runs" with "ticket tracker," and a ticket's human-editable post-run state has no home in `agent_runs`' shape.
- **A DAG/multi-step workflow for triage**, matching the roadmap's assumed Phase-10 dependency. Rejected because that engine does not exist, and single-agent-with-tools is the KISS-correct topology for a classify-and-draft task regardless.
