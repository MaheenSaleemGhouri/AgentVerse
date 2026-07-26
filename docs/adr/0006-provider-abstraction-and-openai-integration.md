# ADR-0006: Provider Abstraction and OpenAI Integration

**Status:** Accepted
**Date:** 2026-07-25
**Numbering note:** `docs/roadmap.md`'s Phase 2 entry names this
`0005-provider-abstraction-and-openai-integration.md`, written before
Phase 1 consumed ADR numbers 0004 and 0005
(`0004-rbac-enforcement-pattern.md`,
`0005-auth-provider-and-schema-ownership.md`). ADRs are numbered by
actual creation order and are immutable once accepted (`CLAUDE.md` §13)
— renumbering an already-accepted ADR to free up "0005" would violate
that immutability, so this decision is recorded as 0006 instead. No
content requirement from the roadmap is affected by the number itself.

## Context

Phase 2 of `docs/roadmap.md` requires the `ProviderAdapter` interface and
its first (OpenAI) implementation to exist *before* any agent-runtime,
worker, or builder concept is written — CLAUDE.md Rule 16 ("Every LLM
call goes through the provider-abstraction layer") must be true from the
first LLM call this codebase ever makes, not retrofitted after
orchestration code already exists directly against an SDK.

This ADR reconfirms `decision-log.md` #7 (Why OpenAI), #9 (Why OpenAI
Agents SDK), and #10 (Why MCP) as the AI stack, and flags their shared
**2026-10-01 re-validation checkpoint** explicitly, per the roadmap's
Phase 2 entry.

## Decision

1. **`ProviderAdapter`** (`orchestration_service/domain/ports/provider_adapter.py`)
   is a `Protocol` with four methods — `chat`, `stream_chat`, `call_tool`,
   `structured_output` — shaped around AgentVerse's own streaming-event
   union (`StreamDelta | StreamDone | StreamError`) and error taxonomy
   (`domain/provider_errors.py`), never the OpenAI SDK's own types or
   tool-call format. This is the interface every future orchestration,
   route, or workflow component is permitted to depend on for LLM calls.
2. **`OpenAIProviderAdapter`** (`orchestration_service/infrastructure/
   providers/openai_adapter.py`) is the sole implementation for this
   phase, and the *only* file in the codebase permitted to
   `import openai` — enforced structurally by a grep-based test, not
   just by convention.
3. Provider errors (rate limit, context-length, content-filter, auth,
   invalid-request, connection/5xx) are translated to AgentVerse's
   internal taxonomy at the adapter boundary; nothing above that
   boundary ever catches an `openai.*` exception.
4. Rate-limit (429) retries use bounded exponential backoff with jitter,
   capped at a fixed ceiling (default 3 attempts, 0.5s base, 8s max
   delay) — never unbounded retrying, which would mask a real outage as
   "still retrying" (this phase's named risk).
5. Token usage is recorded on every completed call via
   `application/cost_accounting.py`, the single source Phase 4 (run-cost
   display) and Phase 7 (billing aggregation) must import, expressed in
   integer **micro-USD** (not integer cents — see that module's
   docstring for why: per-call cost is sub-cent, and rounding to cents
   per call would round nearly every call to zero).
6. A model-routing table *shape* exists (`application/model_routing.py`)
   but is deliberately unconsumed by any logic until Phase 9.
7. **2026-10-01 checkpoint reaffirmed**: decisions #7 (OpenAI), #9
   (Agents SDK), and #10 (MCP) all share this review date in
   `decision-log.md`; this ADR does not move it.

## Consequences

- Every later phase (agent runtime, cost display, billing, multi-agent
  routing, a second provider in Phase 11) builds on a fixed,
  provider-neutral contract instead of an OpenAI-SDK-shaped one.
- Adding a second provider is a new adapter class satisfying the same
  `Protocol` — zero changes to any caller.
- The cost-accounting table's pricing snapshot (dated in
  `cost_accounting.py`) is explicitly *not* invoice-grade until
  `billing-expert` reconciles it against OpenAI's published pricing at
  Phase 7 — this ADR does not claim current billing accuracy.

## Alternatives Considered

- **Import the OpenAI SDK directly from route/workflow code for now,
  abstract later**: rejected — this is precisely the retrofit CLAUDE.md
  Rule 16 exists to prevent; "later" migrations of already-shipped
  direct SDK calls are exactly how provider lock-in becomes permanent.
- **Shape `ProviderAdapter` after OpenAI's own `chat.completions` types**:
  rejected — this phase's own named risk; would force a breaking change
  to every caller the moment Phase 11 adds a second provider.
- **Layer our own retry loop on top of the SDK's built-in retries**:
  rejected — two overlapping, opaque retry policies make the actual
  backoff behavior unverifiable; the SDK's own retries are disabled
  (`max_retries=0`) so this codebase has exactly one retry policy.

## Owner Skill

`ai-architect` (interface/topology ownership), `openai-expert`
(OpenAI-specific implementation), per `decision-log.md` #7's ownership
split.
