# ADR-0001: Clean Architecture Layering for `apps/api` and `apps/worker`

## Context

`CLAUDE.md` §5 mandates a four-layer structure (`domain` → `application` → `infrastructure` → `interface`) for every backend service, dependencies pointing inward, with infrastructure implementing domain-defined ports rather than the reverse. `apps/api` will grow into the orchestration/control-plane gateway and `apps/worker` into the agent-runtime fleet — both are long-lived services expected to carry non-trivial business logic (workspace/RBAC in Phase 1, agent orchestration in Phase 9, DAG workflows in Phase 10). Phase 0 needs to establish this structure before any of that logic exists, so later phases add code onto a settled layout instead of retrofitting one mid-feature (this phase's stated business value, `docs/roadmap.md` Phase 0).

## Decision

Both `apps/api` and `apps/worker` use the identical four-folder layering under `src/<package>/`:

- `domain/` — entities and business rules. Zero framework imports (no FastAPI, no DB driver, no Pydantic-for-I/O). Empty in Phase 0.
- `application/` — use cases/services orchestrating `domain`. Depends inward on `domain` only. Empty in Phase 0.
- `infrastructure/` — concrete adapters implementing ports `domain`/`application` define. Holds `config.py` (typed `Settings`) and `logging.py` (structured JSON logging) in Phase 0 — the first real infrastructure concerns, ahead of any Postgres/Redis/LLM client.
- `interface/` — FastAPI routers, request/response schemas, middleware. Thin orchestration only. Holds only `/health` and `/ready` in Phase 0.

## Consequences

**Positive:** business logic stays testable without I/O once it exists (`domain`/`application` never import FastAPI or a DB driver); infrastructure adapters (Postgres today, a second LLM provider later) are swappable behind ports without touching `interface`; the layout is identical across both Python services, so a contributor who understands one understands the other.

**Negative:** four directories and import-direction discipline for what is, in Phase 0, two services with no business logic at all — real ceremony ahead of real need. Accepted because CLAUDE.md mandates this structure regardless of current complexity, and retrofitting layering onto an already-organically-grown FastAPI app is a strictly worse migration than starting with it.

## Alternatives considered

- **Flat `routers/` + `services/` structure, no formal domain layer.** Rejected: doesn't hold up once Phase 9 (multi-agent orchestration) and Phase 10 (DAG workflows) introduce real domain complexity — would force a disruptive mid-project refactor exactly when the codebase is least able to absorb one.
- **Full hexagonal/ports-and-adapters with explicit `Protocol` classes for every port.** Rejected as over-engineering for Phase 0: CLAUDE.md's four-layer scheme already achieves the same dependency-inversion goal with less ceremony; explicit port interfaces get introduced per-adapter when a second real implementation (e.g. a second LLM provider) actually needs one, not speculatively now.
- **Django-style MVC / ORM-centric structure.** Rejected: no admin-panel or ORM-centric need: FastAPI plus an explicit Clean Architecture layering is what CLAUDE.md §5 mandates, and this alternative doesn't map onto async-first, provider-abstraction-heavy service design.

## Review

**Status:** Approved
**Reviewer:** `architecture-reviewer` (via the AgentVerse Master AI Engineering Team coordination this ADR was authored under)
**Date:** 2026-07-24

Verified against `CLAUDE.md` §5 (layering, dependency direction) and §16 (folder organization by clean-architecture layer). The four-folder scheme matches the constitution's mandate exactly; `domain`/`application` correctly ship empty rather than with speculative entities, consistent with §16's no-speculative-complexity rule. No cross-service coupling introduced (each service gets its own copy of the layering, not a shared framework-coupled base). Approved without conditions — the "ceremony ahead of need" tradeoff named in Consequences is accepted as the correct call given `CLAUDE.md`'s explicit mandate, not a deviation requiring mitigation.
