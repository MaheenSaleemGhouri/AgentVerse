# ADR-0002: Monorepo Tooling & CQRS Non-Adoption Scope

## Context

`decision-log.md` #14 ("Why Monorepo") already settled the org-level decision to use one repository; this ADR is the concrete tooling implementation of that decision for Phase 0's bootstrap. `decision-log.md` #17 ("Why CQRS") already settled that CQRS is **not** adopted platform-wide, with one targeted future exception (billing/usage-panel real-time reads). Both #14 and #17 share an earlier `2026-10-01` review date than the log's other ~23 decisions (most sit at `2027-01-01`), signaling the org considers these two comparatively likely to need revisiting soon — this ADR carries that checkpoint forward explicitly rather than letting it live only in the decision log.

## Decision

**Monorepo tooling:** pnpm workspaces (`pnpm-workspace.yaml`: `apps/web`, `packages/contracts`) for the TypeScript side. `apps/api` and `apps/worker` are independent `uv`-managed Python projects — each with its own `pyproject.toml`/`uv.lock` — not folded into the pnpm workspace. No cross-language build orchestrator (Nx, Turborepo, Bazel) is introduced in Phase 0.

**CQRS scope:** every service uses a single read/write model against Postgres. No separate read-store, no event-sourced write model, anywhere in Phase 0–8 (Macro Phase 1) scope. The one exception decision-log #17 names — billing usage-panel reads from a fast Redis-backed view while durable writes land in `billing_usage_events` — is deferred until Phase 7 actually builds billing; nothing CQRS-shaped is implemented speculatively now.

**Checkpoint:** re-validate both calls no later than **2026-10-01** — specifically: (a) whether the pnpm+uv split still fits once Phase 1–3 add real cross-service dependency surface, and (b) whether CQRS non-adoption still holds once Phase 7 actually designs the billing usage-aggregation path. This checkpoint is the same one carried in ADR-0004 (Phase 2, provider/Agents-SDK/MCP decisions) — one re-validation event covering all of decision-log's `2026-10-01`-dated entries, not four separate reviews.

## Consequences

**Positive:** each toolchain (pnpm, uv) is used the way its ecosystem expects, with no cross-language build-graph tool to learn or debug; CQRS is not built until a real read/write asymmetry exists to justify it (CLAUDE.md §3 KISS, §16 no speculative complexity).

**Negative:** there is no single "install everything" command — a contributor touching both `apps/web` and `apps/api` runs `pnpm install` and `uv sync` separately; two lockfile ecosystems to keep mentally separate. Accepted: the alternative (forcing Python packages under a JS-oriented workspace manager, or vice versa) fights both tools harder than it saves.

## Alternatives considered

- **Nx or Turborepo unifying JS+Python build graphs.** Rejected: no current multi-package build-orchestration need (Phase 0 has one buildable TS package and one placeholder app); adds a tool to learn and keep pinned with no corresponding pain it solves yet.
- **Fully separate repositories per service (polyrepo).** Rejected per `decision-log.md` #14's own reasoning: at current team size, cross-cutting changes (e.g. this Phase 0 bootstrap itself, spanning five directories) are one PR in a monorepo and would be five coordinated PRs in a polyrepo.
- **Full CQRS with separate read/write stores from day one.** Rejected as premature per `decision-log.md` #17 and CLAUDE.md's no-speculative-complexity rule — no service has a read/write asymmetry yet to justify the operational cost of a second store.

## Review

**Status:** Approved
**Reviewer:** `architecture-reviewer` (via the AgentVerse Master AI Engineering Team coordination this ADR was authored under)
**Date:** 2026-07-24

Verified this ADR faithfully implements `decision-log.md` #14 and #17 without silently narrowing or expanding either — it neither introduces a build-orchestration tool the decision log didn't ask for, nor implements any CQRS surface ahead of Phase 7. The `2026-10-01` checkpoint is carried forward with a concrete trigger condition (real cross-service dependency surface for tooling; Phase 7's billing design for CQRS), not left as a vague "revisit later." Approved without conditions.
