# AgentVerse — Implementation Roadmap

*A finer-grained, execution-ready decomposition of the macro-roadmap.*

This document takes `project-memory.md` §12's five macro-phases (MVP foundation → Depth of orchestration → Workflow Automation & collaboration → Growth loops & multi-provider breadth → Full marketplace + enterprise compliance) and decomposes them into 13 sequenced, engineering-ready phases (Phase 0–Phase 12). It is a planning artifact, not a new source of authority: it never contradicts `CLAUDE.md` or `project-memory.md` §12, and no capability belonging to Macro Phase 2 or later ever appears before its correct place in this sequence. Where this document is silent on a standard, `CLAUDE.md` governs; where it is silent on product rationale, `project-memory.md` governs; where it is silent on *why* a technology was chosen, `decision-log.md` governs.

**How to read this document.** Each phase states a goal, the business value, the concrete features/entities/file paths it touches, representative user stories, the engineering tasks, its dependencies (always on a lower-numbered phase — never forward), the exact skill-folder names required, phase-specific risks, testable acceptance criteria, deliverables, applicable `CLAUDE.md` §19 Definition-of-Done items, and its position in the sequential build order. Context for this document was loaded in the fixed priority order defined in `ai-playbook.md` §9: `CLAUDE.md` (full), `project-memory.md` (full, especially §5, §7, §12), `decision-log.md` (full, all 25 decisions), `ai-playbook.md` (full), then the 80-skill roster under `.claude/skills/` (1 `agentverse-master-ai-engineering-team` + 79 role skills), confirmed against the actual directory listing so every "Required skills" reference below is a real folder name.

---

## PHASE 0 — Repo, Toolchain & Infra Bootstrap

**Maps to:** Macro Phase 1 (MVP foundation), root phase, no dependencies.

### Goal
Stand up a buildable, runnable, testable monorepo skeleton — zero product code — so every later phase adds features onto a working foundation rather than negotiating tooling mid-feature.

### Business value
Every week spent later re-litigating repo structure, CI, or local-dev friction is a week not spent on activation-driving features (`project-memory.md` §11). Deciding layering, monorepo scope, and the vector DB choice now — before any code depends on them — avoids a costly mid-flight architecture change and lets Enterprise-Quality concerns (`CLAUDE.md` §2) be architected in from the first commit rather than retrofitted.

### Features
- Monorepo skeleton: `apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `infra/` (`CLAUDE.md` §5; `project-memory.md` §7).
- `docker-compose` local stack: Postgres, Redis, vector DB (pgvector), and stub containers for all three services, health-check-gated startup order.
- Tailwind CSS v4 `@theme` token scaffold (primitive tier only) established **before** shadcn/ui is introduced — strict ordering per `decision-log.md` #11/#12.
- CI skeleton: lint, type-check, unit-test stages as required checks; no deploy job yet (nothing to deploy).
- Observability foundations: structured JSON log schema decided, `/health`/`/ready` convention documented, OTel SDK wiring convention documented — no real spans emitted yet (nothing to trace).
- Git workflow, branch-naming convention, CODEOWNERS, PR template (`CLAUDE.md` §14).
- ADRs: clean-architecture layering; monorepo choice + explicit CQRS non-adoption scope, flagging the shared 2026-10-01 re-validation checkpoint (`decision-log.md` #14, #17); vector DB choice (pgvector decided now, not consumed by any code until Phase 5, per `decision-log.md` #5).

### User stories
- As an **internal engineer**, I want to clone the repo and run one bootstrap command, so that I have all three services and three datastores running locally without tribal knowledge.
- As an **internal engineer**, I want CI to fail my PR on a lint/type error before a human reviews it, so that review time is spent on logic, not style.
- As a **workspace admin (future persona)**, I want the platform's foundation to already assume multi-tenant, observable, reversible operation, so that Enterprise Quality is never a bolt-on retrofit.

### Technical tasks
- Scaffold `apps/web/`, `apps/api/`, `apps/worker/`, `packages/contracts/`, `infra/` per `project-memory.md` §7's tree.
- Write `infra/docker-compose.yml` with Postgres, Redis, pgvector-enabled Postgres extension (or dedicated vector service per ADR), and stub `Dockerfile`s per service in `infra/`.
- Author `docs/adr/0001-clean-architecture-layering.md`, `0002-monorepo-and-cqrs-scope.md` (with the 2026-10-01 checkpoint noted), `0003-vector-database-choice.md`.
- Establish `apps/web/app/globals.css` `@theme` primitive tokens (color/spacing/radius/typography scales) with no components consuming them yet.
- Write `.github/workflows/ci.yml` (lint → type-check → unit, fail-fast), `.github/CODEOWNERS`, `.github/pull_request_template.md`.
- Document logging schema in `docs/systems/logging-schema.md`, health/ready contract in `docs/systems/health-checks.md`, OTel wiring convention in `docs/systems/otel-conventions.md`.
- Create `docs/architecture/service-map.md` (Mermaid stub, to be filled in as services gain real boundaries).

### Dependencies
None — this is the root phase.

### Required skills
`principal-software-architect`, `docker-expert`, `ci-cd-expert`, `git-expert`, `github-expert`, `tailwind-css-expert`, `observability-engineer`, `database-architect`, `vector-database-expert`.

### Risks
- Deciding the vector DB (pgvector vs. managed) this early with no consuming code risks locking in an assumption before Phase 5's actual retrieval-latency/recall needs are known — mitigated by `decision-log.md` #5 explicitly framing it as revisitable.
- A docker-compose health-check ordering mistake across three datastores and three service stubs produces an intermittent "works on my machine" race that looks like a code bug later — must be verified by repeated clean-checkout runs, not a single pass.
- Establishing Tailwind tokens with zero real consuming components risks guessing wrong primitives that get reworked once shadcn/ui lands in Phase 4 — mitigated by keeping the token set minimal (primitive tier only, no component-tier tokens yet).

### Acceptance criteria
- Given a clean checkout, when an engineer runs the documented bootstrap command, then all three services and three datastores start and report healthy within a defined timeout.
- Given an empty/no-op PR, when CI runs, then lint, type-check, and unit stages are all green.
- Given `docs/adr/`, when reviewed, then exactly three ADRs exist in Context/Decision/Consequences/Alternatives format, each with a recorded `architecture-reviewer` verdict.
- Given `apps/web/app/globals.css`, when inspected, then only primitive-tier `@theme` tokens exist — no component built against them yet.

### Deliverables
`infra/docker-compose.yml`, per-service `infra/Dockerfile` stubs, `.github/workflows/ci.yml`, `.github/CODEOWNERS`, `.github/pull_request_template.md`, `docs/adr/0001-clean-architecture-layering.md`, `docs/adr/0002-monorepo-and-cqrs-scope.md`, `docs/adr/0003-vector-database-choice.md`, `docs/architecture/service-map.md`, `docs/systems/logging-schema.md`, `docs/systems/health-checks.md`, `docs/systems/otel-conventions.md`, `apps/web/app/globals.css`.

### Definition of Done
DoD 2 (architecture approved — all three ADRs need a recorded `architecture-reviewer` verdict), 5 (documentation — each stub service ships its `README.md` per `CLAUDE.md` §13), 8 (monitoring — the `/health`/`/ready` and logging conventions are the deliverable itself), 9 (deployment ready — reproducible clean-checkout artifact, even with no deploy job), 10 (final review — go/no-go on "clean checkout to green CI"). DoD 1 (requirements) is satisfied only in the lightweight sense of "internal engineer" as persona — there is no external user-facing requirement yet. DoD 3 (security) is **N/A**: no data flows, no auth surface, nothing to review. DoD 6 (performance) is **N/A**: no measurable user-facing latency surface exists yet. DoD 7 (accessibility) is **N/A**: no UI surface ships in this phase. **Independently shippable** means: any engineer, without asking a teammate anything, can clone the repo, run the bootstrap command, and reach a fully healthy local stack with green CI on an empty PR — the foundation is usable standalone even though no product feature exists yet.

### Estimated implementation order
Position 0 of 12. Root phase — no dependencies, gates every subsequent phase.

---

## PHASE 1 — Workspace, Authentication & RBAC Data Model

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Establish the tenant/isolation root (`workspace`) and its RBAC enforcement so that `workspace_id` scoping — the platform's single most load-bearing invariant — exists before any tenant-owned data is ever written.

### Business value
`CLAUDE.md` Rule 11 makes `workspace_id` scoping absolute and non-negotiable; retrofitting tenant isolation after data exists is far riskier than building it first (`decision-log.md` #23). This phase is also the first real product surface a user touches — sign-up, login, workspace creation — directly gating the activation clock (`project-memory.md` §11).

### Features
- Postgres schema via Alembic migrations: `users`, `workspaces`, `workspace_members` (`role` enum: `owner > admin > member > viewer`).
- `get_current_workspace` FastAPI dependency resolving `workspace_id` from the authenticated identity only — never from client-supplied path/body/query (`CLAUDE.md` Rule 11).
- `require_role` permission-check dependency, deny-by-default, stubbed for future resource types (agents, knowledge bases, billing) that don't exist yet.
- Authentication: email/password + OAuth via a managed provider (Clerk or Better Auth), session cookies (`httpOnly`/`Secure`/`SameSite`), API key issuance/rotation (hashed at rest, shown once).
- `apps/web` shell: login/signup pages, workspace switcher, protected route groups.
- `audit_logs` table (append-only) capturing auth events and role grants/denials from day one.

### User stories
- As an **individual builder**, I want to sign up and create a workspace in under a minute, so that I can start toward my first agent run quickly.
- As a **workspace owner**, I want to invite a teammate at a specific role, so that I control who can view, edit, or administer my workspace.
- As a **workspace admin**, I want a `member`-role teammate to be denied an `owner`-only action, so that I can trust the permission model before I put anything sensitive in the workspace.
- As an **internal engineer**, I want `workspace_id` resolved once in a shared dependency, so that no future route can accidentally trust a client-supplied workspace ID.

### Technical tasks
- Author Alembic migrations under `apps/api/auth-service/infrastructure/migrations/` for `users`, `workspaces`, `workspace_members`, `audit_logs`, each with a tested `downgrade()`.
- Implement `apps/api/auth-service/interface/dependencies/get_current_workspace.py` and `require_role.py`.
- Implement `apps/api/auth-service/application/` use cases for signup, login, workspace creation, member invite/role-change.
- Wire the managed auth provider client behind an adapter in `apps/api/auth-service/infrastructure/auth_provider/`.
- Implement `apps/web/middleware.ts` for thin auth/redirect only (no business logic).
- Build `apps/web/app/(auth)/login`, `(auth)/signup`, `(dashboard)/workspace-switcher` route segments and components.
- Add API key issuance/rotation endpoints under `/api/v1/workspaces/{workspace_id}/api-keys`.

### Dependencies
Phase 0 (repo skeleton, CI, docker-compose Postgres/Redis, ADR-driven layering must exist before any migration or service code is written).

### Required skills
`database-architect`, `authentication-expert`, `authorization-expert`, `fastapi-expert`, `nextjs-expert`, `senior-backend-engineer`, `security-engineer`, `pytest-expert`.

### Risks
- Getting `403` (same-workspace permission gap) vs. `404` (cross-workspace, don't leak existence) semantics wrong is subtle and easy to miss on a single-workspace test fixture — must be tested with at least two workspaces from the start (`decision-log.md` #22).
- Session-cookie misconfiguration (missing `httpOnly`/`Secure`/`SameSite`) is invisible in local dev over HTTP and only surfaces as a real vulnerability in a hardened staging/production TLS environment.
- `require_role` stubbed against resource types that don't exist yet (agents, KBs) risks a mismatched shape once Phase 4/5 land — mitigate by keeping the stub minimal and resource-type-generic rather than guessing future shapes.

### Acceptance criteria
- Given a new user, when they sign up and create a workspace, then a `workspaces` row and an `owner`-role `workspace_members` row exist and they land in the dashboard shell.
- Given a workspace owner invites a teammate as `member`, when that teammate attempts an `owner`-only action, then the request is denied with `403` and the denial is written to `audit_logs`.
- Given a user authenticated in workspace A, when they request a resource scoped to workspace B, then the response is `404`, not `403` (no existence leak).
- Given any new route added after this phase, when it omits the `require_role` dependency, then this is a `code-reviewer`-blocking pattern violation per the Code Review Checklist (`ai-playbook.md` §11).

### Deliverables
Alembic migrations for `users`/`workspaces`/`workspace_members`/`audit_logs`, `apps/api/auth-service/interface/dependencies/{get_current_workspace,require_role}.py`, `apps/web/middleware.ts`, `apps/web/app/(auth)/*`, `apps/web/app/(dashboard)/workspace-switcher`, `docs/adr/0004-rbac-enforcement-pattern.md`.

### Definition of Done
DoD 1, 2, 3, 4, 5, 8, 9, 10 all apply in full — this phase is security-critical (DoD 3 is the primary gate: `security-reviewer` sign-off on the RBAC/tenant-isolation surface is mandatory before merge, per `CLAUDE.md` §10, Rule 11). DoD 6 (performance) applies at a lightweight level — auth/login latency budget is set but not yet under real load. DoD 7 (accessibility) applies to the login/signup/workspace-switcher UI surfaces (keyboard operability, focus management on the invite modal). **Independently shippable** means: a real user can sign up, create a workspace, invite a teammate at a role, and have RBAC enforced in both the allow and deny direction — end to end, with no dependency on any agent/billing feature that doesn't exist yet.

### Estimated implementation order
Position 1 of 12. The single most sequencing-critical phase: `workspace_id` tenant isolation must exist before any tenant-owned data flows in any later phase.

---

## PHASE 2 — LLM Provider Abstraction Layer

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Build the `ProviderAdapter` interface and its first (OpenAI) implementation so that no orchestration, route, or workflow code ever imports a provider SDK directly — the platform's Rule 16 must be true before any agent-runtime code exists, not retrofitted after.

### Business value
Provider concentration risk is an existential risk flagged by `startup-advisor` (`decision-log.md` #7); building the abstraction first, and proving it with a real streamed completion before any agent concept exists, means every later phase (runtime, cost accounting, multi-provider breadth in Phase 11) inherits swappability for free instead of a rewrite.

### Features
- `ProviderAdapter` domain interface (`chat`, `stream_chat`, `call_tool`, `structured_output`) with zero framework/vendor imports.
- OpenAI adapter implementing the interface: async client, streaming, native JSON-schema structured output, bounded exponential backoff with jitter on 429s.
- Model-selection config scaffold (a routing table shape, not yet consumed by any orchestration logic) and cost-accounting primitives (a token→cents table) that Phase 4 (display) and Phase 7 (billing aggregation) will consume, not duplicate.
- A minimal internal-only test route proving the adapter works, with no agent/run/worker concept involved yet.
- ADR reconfirming OpenAI + OpenAI Agents SDK + MCP-consuming as the AI stack, flagging the shared 2026-10-01 re-validation checkpoint (`decision-log.md` #7, #9, #10).

### User stories
- As an **internal engineer**, I want to call one internal endpoint and get a real streamed OpenAI completion through the abstraction, so that I can prove the interface works before any agent-runtime code is written on top of it.
- As a **future engineer adding a second provider (Phase 11)**, I want the interface contract fixed now, so that adding Anthropic later requires a new adapter, not an orchestration rewrite.
- As an **enterprise buyer (future persona)**, I want token usage recorded per call from day one, so that per-workspace/per-run cost is never a bolt-on afterthought.

### Technical tasks
- Define `apps/api/orchestration-service/domain/ports/provider_adapter.py` (the interface, zero vendor imports).
- Implement `apps/api/orchestration-service/infrastructure/providers/openai_adapter.py` implementing the port, with retry/backoff and structured-output support.
- Implement `apps/api/orchestration-service/application/cost_accounting.py` (pure function: token counts → cents, versioned per model) — this is the single source Phase 4/7 must import, never recompute.
- Add `apps/api/orchestration-service/interface/routers/internal_provider_test.py` (internal-only route, not part of `/api/v1`) proving `stream_chat` end-to-end.
- Add `packages/contracts/provider_error_taxonomy.ts`/`.py` translating OpenAI-specific errors (rate limit, context-length, content-filter) to AgentVerse's internal error taxonomy at the boundary.
- Author `docs/adr/0005-provider-abstraction-and-openai-integration.md` with the 2026-10-01 checkpoint flagged.

### Dependencies
Phase 0 (repo/CI/layering must exist). Explicitly **no dependency on Phase 1** — this phase touches no workspace-owned data yet, which is why it can build concurrently with Phase 3.

### Required skills
`ai-architect`, `openai-expert`, `python-expert`, `fastapi-expert`, `principal-software-architect`.

### Risks
- Designing the `ProviderAdapter` interface too OpenAI-shaped (e.g., baking in OpenAI-specific tool-call formats) would defeat the entire point and force a breaking change when Phase 11 adds a second provider — mitigate by deliberately shaping the interface around AgentVerse's own error taxonomy and streaming-event shape, not the OpenAI SDK's.
- Cost-accounting primitives built here but not actually consumed until Phase 4/7 risk silent drift if the token→cents table isn't kept as the *single* source — a future engineer might recompute cost inline in a route, violating DRY (`CLAUDE.md` Rule 3).
- Retry/backoff on 429s without a bounded ceiling could mask a real outage as "still retrying" — must be time-boxed, feeding the documented fallback strategy this phase's ADR commits to.

### Acceptance criteria
- Given the internal test route, when called, then a real OpenAI completion streams back through `ProviderAdapter.stream_chat`, with token usage recorded via `cost_accounting.py`.
- Given a simulated OpenAI 429, when the adapter retries, then it backs off with jitter and stops at a bounded ceiling rather than retrying indefinitely.
- Given any file outside `apps/api/orchestration-service/infrastructure/providers/`, when grepped for `import openai`, then zero matches exist (Rule 16 enforced structurally).
- Given the ADR, when reviewed, then it explicitly states the 2026-10-01 checkpoint alongside decisions 7/9/10 in the decision log.

### Deliverables
`apps/api/orchestration-service/domain/ports/provider_adapter.py`, `apps/api/orchestration-service/infrastructure/providers/openai_adapter.py`, `apps/api/orchestration-service/application/cost_accounting.py`, `packages/contracts/provider_error_taxonomy.py`, `docs/adr/0005-provider-abstraction-and-openai-integration.md`.

### Definition of Done
DoD 1, 2, 4, 5, 6, 9, 10 apply (DoD 6 performance: p50/p95 streaming-token latency budget set and measured even at this internal-only stage). DoD 3 (security) applies at a lightweight level — no user data in scope yet, but secrets handling for the OpenAI API key is reviewed (`CLAUDE.md` Rule 1). DoD 7 (accessibility) is **N/A** — no UI surface in this phase. DoD 8 (monitoring) applies to token-usage recording as the first real telemetry signal. **Independently shippable** means: a backend engineer can call one internal endpoint and receive a real streamed OpenAI completion through the abstraction layer, fully decoupled from and before any agent-runtime, worker, or builder-UI code exists.

### Estimated implementation order
Position 2 of 12. **Parallelization opportunity**: Phase 2 and Phase 3 have no dependency on each other — both depend only on Phase 0 and both gate exclusively into Phase 4. Two engineers/pods can build them concurrently to compress calendar time.

---

## PHASE 3 — Background Worker & Queue Infrastructure

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Stand up `apps/worker`'s Redis-backed queue, retry/DLQ mechanics, and a distributed-lock primitive using a trivial, agent-agnostic "echo job" — proving the infrastructure before any agent-specific execution logic exists.

### Business value
`CLAUDE.md` Rule 14 makes background execution for long-running work non-negotiable; proving queue reliability (retry, DLQ, idempotent redelivery) against a trivial job now means Phase 4's real agent-run execution inherits already-hardened infrastructure instead of debugging queue mechanics and agent logic simultaneously.

### Features
- `apps/worker` service: Redis Streams-backed queue (consumer groups, `XACK`, `XPENDING`), bounded retry with exponential backoff, dead-letter queue.
- A generic `Job` domain model, proven via a trivial "echo job" handler — no agent/run concept yet.
- A distributed lock primitive (Redis-backed, TTL'd) preventing duplicate submission of the same logical job — the exact primitive Phase 4's idempotent run-submission endpoint will build on.
- Redis pub/sub channel convention `run:{run_id}:events` established as **infra-only scaffolding** — explicitly not wired to any SSE feature yet (per `decision-log.md` #19, SSE must accompany, not precede, the real run feature in Phase 4).
- Worker containerization with OS-level resource limits (per `linux-expert`'s remit) so a runaway job can't starve co-located workers.

### User stories
- As an **internal engineer**, I want to enqueue a trivial job and watch it execute asynchronously, so that I can verify queue mechanics before any product feature depends on them.
- As an **internal engineer**, I want a job to land in the dead-letter queue after exhausting retries, so that I can verify failure handling doesn't fail silently.
- As a **future workspace owner (Phase 4+)**, I want duplicate run submissions (e.g., a double-click or client retry) to never double-execute, so that I'm never charged twice for one action.

### Technical tasks
- Scaffold `apps/worker/src/queue/` (Redis Streams client, consumer group setup, retry/backoff policy, DLQ handler).
- Implement `apps/worker/src/jobs/echo_job.py` as the proof-of-concept generic job handler.
- Implement `apps/worker/src/locks/distributed_lock.py` (Redis `SET NX PX` pattern with safe release).
- Establish the `run:{run_id}:events` pub/sub channel convention in `docs/systems/redis-channels.md` — documented as scaffolding only, not yet consumed by any client.
- Add an internal-only enqueue endpoint (`apps/api/orchestration-service/interface/routers/internal_job_test.py`) to submit echo jobs for verification.
- Write `infra/Dockerfile.worker` with non-root user and resource limits (`linux-expert`, `docker-expert`).
- Add queue depth/DLQ-size metrics to the observability foundation established in Phase 0.

### Dependencies
Phase 0 (repo/CI/docker-compose Redis must exist). Explicitly **no dependency on Phase 1 or Phase 2** — this phase touches no workspace-owned data and no LLM provider.

### Required skills
`system-designer`, `redis-expert`, `senior-backend-engineer`, `docker-expert`, `linux-expert`, `observability-engineer`.

### Risks
- Building the pub/sub channel convention this early without a real SSE consumer risks guessing the wrong event shape — mitigate by treating it as a naming/scaffolding decision only, deferring the actual event schema to Phase 4 where a real consumer exists.
- Redis Streams consumer-group misconfiguration (e.g., missing `XACK`) silently causes at-least-once delivery to degrade into "processed forever, never acknowledged," invisible until the stream backs up under load.
- A distributed lock without a correctly safe TTL/release pattern can either deadlock (lock never releases) or fail to prevent duplicates (lock released too early) — both failure modes are easy to introduce and hard to catch without a dedicated concurrency test.

### Acceptance criteria
- Given an echo job enqueued via the internal test endpoint, when the worker picks it up, then it executes and is acknowledged (`XACK`'d) exactly once.
- Given a job configured to always fail, when it exhausts its bounded retry count, then it lands in the dead-letter queue with its failure reason recorded.
- Given two identical job submissions within the lock's TTL window, when both attempt to enqueue, then only one executes.
- Given the worker container, when run under a simulated memory-heavy job, then the configured resource limit (not the host) is what terminates it.

### Deliverables
`apps/worker/src/queue/`, `apps/worker/src/jobs/echo_job.py`, `apps/worker/src/locks/distributed_lock.py`, `infra/Dockerfile.worker`, `docs/systems/redis-channels.md`, `docs/systems/queue-dlq-policy.md`.

### Definition of Done
DoD 1, 2, 4, 5, 6, 8, 9, 10 apply (DoD 6 performance: queue-throughput and job-latency budgets set and measured against the echo job). DoD 3 (security) is lightweight — no tenant data in scope yet, but the internal test endpoint must not be reachable from `/api/v1`. DoD 7 (accessibility) is **N/A** — no UI surface in this phase. **Independently shippable** means: an engineer can enqueue a trivial job via an internal endpoint, watch it execute asynchronously, observe retry/DLQ behavior under a forced failure, and read queue-depth metrics — fully proven infrastructure with zero product/agent feature attached yet.

### Estimated implementation order
Position 3 of 12. **Parallelization opportunity**: Phase 2 and Phase 3 have no dependency on each other — both depend only on Phase 0 and both gate exclusively into Phase 4. This is the one explicit, real opportunity to compress calendar time by running two pods concurrently.

---

## PHASE 4 — Single-Agent Builder, Runtime & Live Execution (SSE)

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Ship the platform's first real activation moment: a user builds a single-agent-with-tools, runs it, and watches live streaming execution with correct cost — Phase 2's provider abstraction and Phase 3's queue infrastructure fused into one product feature for the first time.

### Business value
This is the canonical activation metric made real: `run_completed` within 24h of workspace creation (`CLAUDE.md` §1; `project-memory.md` §11). Everything before this phase was infrastructure; this phase is the first thing a paying customer actually experiences, and it is the foundation every later orchestration/workflow phase extends rather than replaces.

### Features
- `agents`/`agent_versions` schema — an agent is stored, versioned configuration, never hand-authored outside the builder (`CLAUDE.md` §4 Agents).
- Visual agent builder canvas in `apps/web` for single-agent-with-tools authoring — the **first legitimate use of shadcn/ui** (valid now that Tailwind tokens exist from Phase 0; strict ordering per `decision-log.md` #11/#12).
- `agent_runs`/`agent_run_steps` schema.
- "Run Agent" submits a job to Phase 3's queue, executed in `apps/worker` via Phase 2's `ProviderAdapter`.
- SSE endpoint streaming `agent_run_steps` events live from Phase 3's `run:{run_id}:events` Redis pub/sub channel to the browser — the mandated SSE-with-execution pairing (`decision-log.md` #19).
- Live trace viewer with per-run cost display, using Phase 2's `cost_accounting.py` primitive (displayed, never recomputed).
- Idempotent run-submission endpoint (`Idempotency-Key` header) built on Phase 3's distributed lock.

### User stories
- As an **individual builder**, I want to build a single agent with one tool on a visual canvas, so that I reach a working agent without writing orchestration code myself.
- As an **individual builder**, I want to run my agent and watch each step stream live, so that I always know what is happening right now and whether it's working (`CLAUDE.md` §2 Transparency).
- As an **AI engineer**, I want to see the exact cost of a run as it completes, so that I never get a surprise on the invoice later.
- As a **workspace admin**, I want a duplicate run submission (e.g., a flaky client retry) to never trigger a second execution, so that I'm not double-billed.

### Technical tasks
- Alembic migrations for `agents`, `agent_versions`, `agent_runs`, `agent_run_steps` under `apps/api/orchestration-service/infrastructure/migrations/`, each `workspace_id`-scoped with a leading index.
- Build the canvas: `apps/web/app/(dashboard)/agents/[agentId]/builder/` client-rendered canvas/node/edge layer inside a server-rendered shell; `apps/web/components/agents/` product components composed from `apps/web/components/ui/` shadcn primitives.
- Implement `apps/api/orchestration-service/application/run_agent.py` (use case: validate agent config, acquire Phase 3's lock, enqueue job).
- Implement the worker-side executor `apps/worker/src/jobs/agent_run_job.py` calling `ProviderAdapter.stream_chat`, writing `agent_run_steps` and publishing to `run:{run_id}:events`.
- Implement the SSE route `apps/api/orchestration-service/interface/routers/run_stream.py` (`StreamingResponse` reading Redis pub/sub, cleaning up subscription on client disconnect).
- Build `apps/web/lib/hooks/useAgentRunStream.ts` (buffered/throttled flush, not per-event `setState`) and the trace-viewer UI.
- Add `Idempotency-Key` handling to the run-submission endpoint per `CLAUDE.md` §7.

### Dependencies
Phase 1 (workspace/RBAC must exist — agents are workspace-owned resources). Phase 2 (the provider abstraction the worker executor calls). Phase 3 (the queue/lock/pub-sub infrastructure the run pipeline is built on).

### Required skills
`ai-architect`, `openai-agents-sdk-expert`, `fastapi-expert`, `nextjs-expert`, `react-expert`, `shadcn-ui-expert`, `system-designer`, `opentelemetry-expert`, `accessibility-expert`.

### Risks
- The canvas is the first genuinely complex client-rendered interactive surface in the product — a naive implementation risks re-render storms under streaming updates if high-frequency log entries aren't isolated from the canvas render tree (`CLAUDE.md` §6 React 19).
- SSE connection cleanup on disconnect is easy to get wrong under real network conditions (client closes tab mid-run) — a leaked Redis subscription is a documented review-gate item (`decision-log.md` #19) and will only surface under load, not in a quick manual test.
- Mixing Phase 2's cost primitive with a locally-recomputed cost display (instead of importing `cost_accounting.py`) would silently violate DRY and risk the trace-viewer showing a number that later disagrees with Phase 7's billing aggregation.

### Acceptance criteria
- Given a workspace member builds a single agent with one tool, when they click "Run," then a job is enqueued idempotently and the run reaches a terminal state (`success`/`error`) without inline blocking of the request.
- Given a run is in progress, when the browser is connected via SSE, then each `agent_run_step` streams live with correct ordering and the trace viewer shows a running cost total sourced from `cost_accounting.py`.
- Given the browser tab is closed mid-run, when the server detects the disconnect, then the Redis subscription and any background task are torn down (no leak).
- Given the same `Idempotency-Key` is replayed, when the run-submission endpoint receives it twice, then only one run is created and the second request returns the original response.

### Deliverables
Migrations for `agents`/`agent_versions`/`agent_runs`/`agent_run_steps`, `apps/web/app/(dashboard)/agents/[agentId]/builder/`, `apps/web/components/agents/`, `apps/web/lib/hooks/useAgentRunStream.ts`, `apps/api/orchestration-service/application/run_agent.py`, `apps/worker/src/jobs/agent_run_job.py`, `apps/api/orchestration-service/interface/routers/run_stream.py`, `docs/adr/0006-sse-run-streaming-contract.md`.

### Definition of Done
All 10 DoD items apply in full — this is the first genuine end-to-end user-facing feature. DoD 3 (security) is a primary gate alongside DoD 7 (accessibility, first real canvas + streaming UI: keyboard operability, ARIA live regions for the log viewer per `CLAUDE.md` §15). DoD 6 (performance) sets the canvas and streaming-log Core Web Vitals/latency budgets referenced by every later UI phase. **Independently shippable** means: a beta user can build a single agent with one tool, run it, and watch live streaming execution with a correct cost readout — the platform's first fully self-contained, demoable, activation-driving feature.

### Estimated implementation order
Position 4 of 12. Converges Phase 2 and Phase 3's parallel tracks; the point at which both parallel pods must synchronize before proceeding.

---

## PHASE 5 — Knowledge Bases & RAG

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Give agents grounded, cited answers over per-workspace documents via a testable retrieval pipeline (rewrite → hybrid retrieve → rerank → assemble), attachable to any agent built in Phase 4.

### Business value
Grounded, cited answers directly address the "opacity" problem named in `project-memory.md` §2 and differentiate against black-box chat wrappers; RAG is also a prerequisite for the Phase 9 memory-v2 vector usage and Phase 10 marketplace search, so its tenancy and versioning discipline set the pattern the rest of the platform's vector usage inherits.

### Features
- `knowledge_bases`/`kb_documents`/`kb_chunks` schema, `workspace_id`-scoped throughout.
- Vector DB indexing finalized against Phase 0's ADR (pgvector, HNSW indexes), embeddings tagged with `embedding_model`/`embedding_model_version`.
- Ingestion pipeline (upload → content-sniff → chunk → embed) as a Phase 3 background job — never inline in a request.
- Retrieval pipeline: query rewrite, hybrid keyword+vector retrieve, rerank, context assembly within the target model's real token budget, with citation metadata (`document_id`/`chunk_id`) flowing through every stage.
- Agent builder UI extended: an "Attach Knowledge Base" step on the canvas.

### User stories
- As an **individual builder**, I want to upload a PDF to a knowledge base and attach it to my agent, so that it answers questions grounded in my own documents.
- As an **AI engineer**, I want every grounded answer to carry a citation back to the source chunk, so that I can verify correctness rather than trust a black box.
- As a **workspace admin**, I want my workspace's knowledge base completely isolated from every other workspace's, so that there is no possibility of cross-tenant data leakage in retrieval.

### Technical tasks
- Alembic migrations for `knowledge_bases`, `kb_documents`, `kb_chunks` (the last carrying `embedding`, `embedding_model`, `embedding_model_version`, `workspace_id`) under `apps/api/orchestration-service/infrastructure/migrations/`.
- Implement chunking functions as pure, unit-tested functions in `apps/api/orchestration-service/domain/chunking/` (content-aware: prose vs. markdown vs. code).
- Implement the ingestion job `apps/worker/src/jobs/kb_ingest_job.py`, idempotent per `(kb_document_id, content_hash)`.
- Implement the retrieval pipeline as a distinct testable module: `apps/api/orchestration-service/application/retrieval/{rewrite,retrieve,rerank,assemble}.py`.
- Extend the builder canvas: `apps/web/components/agents/knowledge-base-attach.tsx`.
- Add file-upload handling with content-sniffing, size caps, and generated filenames outside the web root (`CLAUDE.md` §10).

### Dependencies
Phase 4 (an agent must exist to attach a KB to; the run pipeline is what ultimately consumes retrieved context). Phase 0's vector-DB ADR (storage mechanics decided there, consumed here for the first time).

### Required skills
`vector-database-expert`, `rag-expert`, `database-architect`, `python-expert`, `secure-coding-expert`, `fastapi-expert`.

### Risks
- Post-filtering an unscoped top-k by `workspace_id` instead of pre-filtering both leaks tenant data and degrades recall — a single reversed filter order here is the exact failure mode `decision-log.md` #5 and #23 warn about.
- Mixing embedding-model versions in one similarity search produces meaningless relevance scores silently — no error is thrown, the answer just quietly gets worse, which is hard to catch without an eval set.
- Chunking strategy tuned only against one document type (e.g., prose) may silently degrade recall for code or markdown-heavy uploads if chunking isn't genuinely content-aware per document type.

### Acceptance criteria
- Given a user uploads a PDF and attaches it to an agent, when they ask a grounded question, then the answer includes a citation traceable to the source chunk.
- Given two workspaces each with a knowledge base, when workspace A's agent retrieves, then zero chunks from workspace B are ever returned, verified via a cross-tenant fixture test.
- Given the same document is re-uploaded unchanged, when ingestion runs again, then no duplicate chunks are created (idempotent on `content_hash`).
- Given a retrieval query, when context is assembled, then the total token count respects the target model's real budget (system prompt + history + reserved output accounted for).

### Deliverables
Migrations for `knowledge_bases`/`kb_documents`/`kb_chunks`, `apps/api/orchestration-service/domain/chunking/`, `apps/worker/src/jobs/kb_ingest_job.py`, `apps/api/orchestration-service/application/retrieval/`, `apps/web/components/agents/knowledge-base-attach.tsx`, a labeled eval set for retrieval quality (recall@k/precision@k/groundedness).

### Definition of Done
DoD 1–6, 8–10 apply. DoD 3 (security) is a primary gate: cross-tenant retrieval isolation and file-upload hardening are both explicit `security-reviewer` checklist items. DoD 7 (accessibility) applies to the KB-attach UI surface (not the retrieval logic itself). **Independently shippable** means: a user uploads a document, attaches it to an existing Phase 4 agent, asks a question, and receives a grounded, cited answer — with workspace isolation holding under a two-workspace test.

### Estimated implementation order
Position 5 of 12. Depends only on Phase 4; has no hard mutual dependency with Phase 6 (see Council Review §c for the parallelization note).

---

## PHASE 6 — Tool-Calling, Central Tool-Execution Boundary & MCP

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Give agents the ability to call native and MCP-sourced tools, all routed through one central, logged, rate-limited, sandboxed execution boundary — with MCP scoped strictly to *consuming* third-party servers (AgentVerse's own MCP server surface is explicitly out of scope until Phase 12).

### Business value
Tool calling is what turns an agent from a chatbot into something that acts — a core differentiator named in `project-memory.md` §4 Integrations; but it is also the platform's largest AI-specific threat surface (prompt injection via tool output, agent-initiated SSRF), so this phase is where `CLAUDE.md` §10's AI-specific threat-surface rules become real code, not policy.

### Features
- `tool_calls` schema, `workspace_id`-scoped, recorded from the single central tool-execution boundary — nothing bypasses it, including SDK-wrapped tools.
- Native tool registry (a small first-party set) plus `mcp_connection` schema for consuming third-party MCP servers over stdio (co-located/trusted) or SSE (remote/third-party).
- Tool discovery UI in the builder: connect an MCP server, browse its tools, attach to an agent.
- Security hardening: egress control point denying RFC1918/link-local/metadata/loopback for every agent-initiated outbound call; tool results treated as untrusted content and structurally isolated before re-entering agent context, identical treatment to RAG chunks from Phase 5.

### User stories
- As an **AI engineer**, I want to connect a third-party MCP server and see its tools in a picker, so that I can extend my agent without writing a bespoke connector.
- As a **workspace admin**, I want every tool call — native or MCP — logged with its arguments and result, so that I can audit exactly what my agents did.
- As a **security-conscious enterprise buyer**, I want an agent-initiated call to an internal/metadata IP address to be blocked by default, so that a compromised or misconfigured tool can't be used for SSRF.

### Technical tasks
- Alembic migrations for `tool_calls` and `mcp_connection` (the latter storing only a reference to workspace-scoped, secrets-manager-resolved credentials — never the credential itself).
- Implement the central tool-execution boundary: `apps/api/integration-service/application/execute_tool.py` — single choke point for validation (tool-call arguments validated against schema before execution), sandboxing, timeouts, output-size limits, and `tool_calls` logging.
- Implement the egress control point: `apps/api/integration-service/infrastructure/egress_guard.py`, deny-by-default to RFC1918/link-local/`169.254.0.0/16`/loopback.
- Implement MCP client adapters: `apps/api/integration-service/infrastructure/mcp/{stdio_client,sse_client}.py`.
- Build the tool-discovery/connect UI: `apps/web/app/(dashboard)/agents/[agentId]/builder/tools/`.
- Ensure a failing/unreachable MCP server disables only its own tools for that run with a clear trace event — never crashes the run.

### Dependencies
Phase 4 (agents and runs must exist for a tool call to attach to and be recorded against). Phase 5 is not a hard dependency but shares the "untrusted external content" isolation pattern — see Council Review §c on the Phase 5/6 parallelization note.

### Required skills
`mcp-expert`, `security-engineer`, `owasp-expert`, `secure-coding-expert`, `fastapi-expert`, `openai-agents-sdk-expert`.

### Risks
- A vague or missing tool description degrades tool selection as badly as a bad system prompt (`decision-log.md` #10) — this is a content-quality risk, not just a code-correctness one, and is easy to under-invest in.
- The egress control point is only as good as its coverage of edge-case IP ranges (IPv6 link-local, DNS rebinding to a metadata IP after initial validation) — a naive allowlist/denylist implementation is a real SSRF gap, not a theoretical one.
- Treating MCP tool results as trusted-by-default (skipping the same structural isolation RAG chunks get) is the single most likely regression here, since it "looks like" ordinary function output rather than external untrusted content.

### Acceptance criteria
- Given a user connects an MCP server over SSE, when they open the tool picker, then its tools appear with their schemas, and attaching one to an agent works.
- Given an agent runs with an attached MCP tool, when the run completes, then the tool call (arguments, result, timing) is recorded in `tool_calls` and visible in the Phase 4 trace viewer.
- Given a tool attempts to call an RFC1918 or metadata-range address, when the call is attempted, then the egress control point blocks it and the run's trace records a clear denial reason.
- Given an MCP server is unreachable mid-run, when the agent needs one of its tools, then only that server's tools are disabled for the run — the run itself does not crash.

### Deliverables
Migrations for `tool_calls`/`mcp_connection`, `apps/api/integration-service/application/execute_tool.py`, `apps/api/integration-service/infrastructure/egress_guard.py`, `apps/api/integration-service/infrastructure/mcp/`, `apps/web/app/(dashboard)/agents/[agentId]/builder/tools/`, a `security-reviewer` sign-off record specifically covering SSRF and prompt-injection-via-tool-output.

### Definition of Done
All 10 DoD items apply. DoD 3 (security) is the primary, non-negotiable gate for this phase — `security-reviewer` sign-off with zero unresolved blocking findings on the SSRF and injection surfaces is required before merge, per `CLAUDE.md` Rule 6. DoD 7 (accessibility) applies to the tool-picker UI. **Independently shippable** means: a user connects an MCP server, sees its tools in the picker, attaches one to an agent, runs it, sees the tool call recorded in the trace, and the SSRF/injection protections hold under a deliberate adversarial test.

### Estimated implementation order
Position 6 of 12.

---

## PHASE 7 — Billing & Stripe Integration

**Maps to:** Macro Phase 1 (MVP foundation).

### Goal
Meter real usage from Phase 4's per-run cost/token data into durable `billing_usage_events`, and let a workspace owner subscribe via Stripe with quota enforcement — correct to the cent, never double-billed under webhook retries.

### Business value
Billing correctness is a named non-negotiable (`CLAUDE.md` Rule 15, Rule 13) and directly gates revenue; this phase turns the platform from a working product into a paying-customer-ready one, and it must consume — never recompute — the cost primitive Phase 2 established and Phase 4 already displays, or two representations of "cost" will silently disagree.

### Features
- `billing_subscriptions`/`billing_usage_events`/`invoices`/`api_keys` (scope) schema, money always integer cents.
- Usage-metering pipeline aggregating Phase 4's per-run cost/token data into durable `billing_usage_events` — Redis usage counters serve the in-product Usage panel, `billing_usage_events` is the sole source for actual invoicing (`decision-log.md` #17).
- Stripe Checkout + Billing Portal integration; idempotent webhook handler (signature-verified, event-ID idempotent, reconciled nightly against Stripe's truth).
- Four tiers (Free/Pro/Team/Enterprise) with quota gating enforced at the API layer.
- Subscription lifecycle state machine (`trial`/`active`/`past_due`/`canceled`) with dunning.

### User stories
- As a **workspace owner**, I want to subscribe to a paid tier via Stripe Checkout, so that I can unlock higher usage quotas without leaving the product.
- As an **individual builder on Free**, I want to see my usage against quota in-product before I hit a limit, so that I'm never surprised by a blocked run.
- As a **finance stakeholder**, I want a Stripe webhook retry to never double-charge or double-count usage, so that billing is trustworthy to the cent.

### Technical tasks
- Alembic migrations for `billing_subscriptions`, `billing_usage_events` (partitioned by `created_at` from the first migration per `CLAUDE.md` §8), `invoices`.
- Implement the usage-aggregation pipeline `apps/api/billing-service/application/aggregate_usage.py`, consuming Phase 2's `cost_accounting.py` output recorded per Phase 4 run — never recomputing cost independently.
- Implement Stripe adapters `apps/api/billing-service/infrastructure/stripe/{checkout,billing_portal,webhook_handler}.py`, with signature verification and an idempotency table keyed on Stripe event ID.
- Implement quota-gating middleware in `apps/api/orchestration-service/interface/dependencies/enforce_quota.py`, applied before a run is enqueued.
- Build `apps/web/app/(dashboard)/settings/billing/` (plan picker, usage panel, Billing Portal link).
- Implement the subscription state machine and dunning logic in `apps/api/billing-service/application/subscription_lifecycle.py`.

### Dependencies
Phase 1 (a workspace must exist to attach a subscription to). Phase 4 (the per-run cost/token data this phase's usage pipeline aggregates must already be produced and displayed).

### Required skills
`billing-expert`, `stripe-integration-expert`, `saas-strategist`, `postgresql-expert`, `fastapi-expert`, `secure-coding-expert`.

### Risks
- Recomputing cost independently in the billing-aggregation path instead of importing Phase 2/4's existing primitive is the single most likely way this phase silently violates DRY and produces a billing number that disagrees with what the user already saw in the trace viewer.
- Webhook out-of-order delivery (Stripe guarantees at-least-once, not ordered) can corrupt subscription state if the handler applies events by arrival order instead of by object state — a documented sharp edge in `decision-log.md` #21.
- Quota-gating enforced only in the UI (not at the API layer) would be silently bypassable by direct API calls — must be a server-side dependency, never a client-side-only check.

### Acceptance criteria
- Given a workspace owner completes Stripe Checkout, when the webhook fires, then `billing_subscriptions` reflects the new tier and quota gating updates accordingly.
- Given the same Stripe webhook event is redelivered, when the handler processes it twice, then the resulting state is identical to processing it once (no double-count, no double-charge).
- Given a workspace exceeds its run quota, when a new run is submitted, then the API returns `429` with `quota_exceeded` and a `retry_after` where known, before any expensive work begins.
- Given `billing_usage_events` and the Phase 4 trace-viewer cost display for the same run, when compared, then they agree exactly (single source of truth held).

### Deliverables
Migrations for `billing_subscriptions`/`billing_usage_events` (partitioned)/`invoices`, `apps/api/billing-service/application/{aggregate_usage,subscription_lifecycle}.py`, `apps/api/billing-service/infrastructure/stripe/`, `apps/api/orchestration-service/interface/dependencies/enforce_quota.py`, `apps/web/app/(dashboard)/settings/billing/`.

### Definition of Done
All 10 DoD items apply. DoD 3 (security) covers webhook signature verification and idempotency as a specific checklist item. DoD 6 (performance) covers quota-check latency (must not add meaningful overhead to run submission). DoD 7 (accessibility) applies to the billing settings UI. **Independently shippable** means: a workspace owner can subscribe via Stripe Checkout, see accurate usage against quota in-product, and have quota enforcement hold correctly — with a nightly reconciliation job proving webhook delivery didn't drift `billing_subscriptions` from Stripe's actual state.

### Estimated implementation order
Position 7 of 12. Depends on both Phase 1 and Phase 4 — satisfied by construction since both are already built.

---

## PHASE 8 — Prompt Versioning, Eval Harness & Marketplace Starter Templates

**Maps to:** Macro Phase 1 (MVP foundation) — this phase closes Macro Phase 1.

### Goal
Make prompts versioned, eval-gated artifacts, and ship a first-party marketplace of starter templates — so a brand-new user reaches a working, eval-passing agent within minutes, fully delivering on Macro Phase 1's activation goal.

### Business value
This is the phase that makes Macro Phase 1's promise real end-to-end: `project-memory.md` §3's "sign up → modify a marketplace template → run → read the trace → iterate" workflow only exists once starter templates ship, and no prompt is trustworthy in production without the eval-before-ship discipline `decision-log.md` #25 establishes.

### Features
- `prompt_template`/`prompt_version` schema with version history/diffing — a prompt is never an inline string literal.
- Eval harness: golden datasets, scoring rubrics (deterministic checks first, reference-anchored LLM-as-judge only where needed), cost/latency tracked per variant — built and proven **before** any prompt-shipping workflow is exposed to end users.
- A CI-style gate: a `prompt_version` cannot transition to `active` until it passes its golden-dataset eval run.
- Marketplace of starter templates: `agent_template` schema, browse/install flow, seeded **first-party only** (third-party publishing is explicitly Phase 11 scope).

### User stories
- As a **brand-new individual builder**, I want to install a starter template instead of starting from a blank canvas, so that I reach a working agent in the fewest possible steps.
- As a **prompt-engineering internal user**, I want to change a system prompt and have it automatically re-run against its golden dataset, so that a regression is caught before it reaches users.
- As a **workspace admin**, I want to browse a catalog of first-party templates by category, so that I can find a starting point close to my use case.

### Technical tasks
- Alembic migrations for `prompt_template`, `prompt_version` (immutable once shipped), `agent_template` (first-party-only for now).
- Implement the eval harness `apps/api/orchestration-service/application/eval_harness/{golden_dataset,scoring_rubric,regression_runner}.py`, structural/behavioral assertions only, no exact-text matching.
- Implement the "cannot go active without passing eval" gate in `apps/api/orchestration-service/application/promote_prompt_version.py`.
- Build the marketplace browse/install UI: `apps/web/app/(marketplace)/templates/`, ISR-cached and SEO-optimized per `CLAUDE.md` §6.
- Seed a first batch of first-party starter templates (agent config + prompt versions + a passing eval record each).

### Dependencies
Phase 4 (agents/agent_versions must exist for a template to instantiate into). Phase 5 and Phase 6 (a realistic starter template plausibly includes a knowledge base and/or a tool, so both should exist to make templates genuinely representative).

### Required skills
`prompt-engineer`, `rag-expert`, `testing-architect`, `nextjs-expert`, `seo-expert`, `growth-engineer`.

### Risks
- Shipping the marketplace browse UI before the eval gate is enforced would let an unvalidated prompt reach new users on their very first interaction with the product — the highest-stakes place for a silent quality regression to land.
- LLM-as-judge scoring without a fixed reference-anchored rubric drifts over time and produces an eval harness that "passes" things it shouldn't — a documented risk in `decision-log.md` #25.
- Combining eval-harness and marketplace work into one phase (done deliberately here, see Council Review §c) risks under-resourcing one half if not explicitly tracked as two work-streams within the phase.

### Acceptance criteria
- Given a prompt version fails its golden-dataset eval, when someone attempts to promote it to `active`, then the promotion is blocked with the failing eval results shown.
- Given a brand-new user, when they install a starter template, then they have a working, eval-passing agent ready to run within minutes, with no manual configuration required.
- Given the marketplace browse page, when crawled, then it is ISR-cached, has correct SEO metadata, and canonicalizes/`noindex`es filtered views per `CLAUDE.md` §6.
- Given the target model version changes, when the regression runner is triggered, then the full eval suite re-runs, not only on prompt-text changes.

### Deliverables
Migrations for `prompt_template`/`prompt_version`/`agent_template`, `apps/api/orchestration-service/application/eval_harness/`, `apps/api/orchestration-service/application/promote_prompt_version.py`, `apps/web/app/(marketplace)/templates/`, a seeded first-party template catalog with passing eval records.

### Definition of Done
All 10 DoD items apply. DoD 4 (tests) is the primary emphasis — the eval harness itself is the deliverable, and DoD 4's "no exact-string assertions on LLM output" is directly enforced here. DoD 6 (performance) covers marketplace page Core Web Vitals (ISR-cached). DoD 7 (accessibility) applies to the marketplace browse/install UI. **Independently shippable** means: a brand-new, previously-unseen user can sign up, install a first-party starter template, and get a working, eval-passing agent running — Macro Phase 1's full activation loop is now deliverable end to end with no manual intervention.

### Estimated implementation order
Position 8 of 12. Closes Macro Phase 1. Could in principle split into two separate phases (eval harness alone; marketplace alone) — deliberately kept combined; see Council Review §c for the rationale.

---

## PHASE 9 — Multi-Agent Orchestration & Model Routing

**Maps to:** Macro Phase 2 (Depth of orchestration).

### Goal
Layer real multi-agent topologies (supervisor-worker, planner/executor/critic, sequential handoff) over Phase 4's single-agent primitives, add documented model-routing fallbacks, and give agents a durable, RAG-separate memory — the platform's first orchestration-depth differentiator.

### Business value
Orchestration depth is named directly as the moat (`project-memory.md` §1 Vision, "orchestration + agent memory + observability"); this phase is where that moat first becomes real product, strictly sequenced after the single-agent MVP so it extends proven infrastructure rather than competing with it for engineering attention during Macro Phase 1.

### Features
- Multi-agent topologies (supervisor-worker, planner/executor/critic, sequential handoff) built as new orchestration graphs **over** Phase 4's `agents`/`agent_versions` — never a rewrite of the single-agent primitive.
- Typed, versioned `handoff_contract` in `packages/contracts` — a summary plus pointers (run/trace ID), never a raw transcript dump (`CLAUDE.md` §4 Multi-Agent Collaboration).
- Model-routing with documented fallback chains, extending Phase 2's `ProviderAdapter` abstraction — routing decisions reference the interface, never a hardcoded model.
- Agent memory v2: vector-backed via Phase 5's vector-DB infrastructure, but in a **logically separate namespace/collection** from the RAG knowledge-base store — must never cross-contaminate.
- The SSE trace viewer (Phase 4) extended for multi-agent handoffs — still SSE, not WebSockets, per `decision-log.md` #19/#20.

### User stories
- As an **AI engineer**, I want to configure a supervisor-worker team instead of a single agent, so that I can decompose a task too complex for one agent.
- As an **AI engineer**, I want to watch a live trace of agent-to-agent handoffs, so that I can see exactly what context was passed and why.
- As a **workspace owner**, I want a documented fallback model to actually trigger when the primary provider is degraded, so that my agents keep working through an outage.

### Technical tasks
- Design topology graphs in `apps/api/orchestration-service/domain/topologies/{supervisor_worker,planner_executor_critic,sequential_handoff}.py`, each composed from the existing single-agent execution primitive.
- Define `packages/contracts/handoff_contract.ts`/`.py` (typed, versioned payload schema).
- Extend `apps/api/orchestration-service/application/cost_accounting.py`'s routing-table consumer into `apps/api/orchestration-service/application/model_routing.py`, with a documented fallback chain per task type.
- Implement agent memory v2: `apps/api/orchestration-service/infrastructure/memory/session_memory_store.py`, backed by a distinct vector-DB collection/namespace from Phase 5's KB store, with Redis/Postgres session lifecycle backing per `CLAUDE.md` §4 Memory.
- Extend `apps/web/lib/hooks/useAgentRunStream.ts` and the trace viewer to render handoff events with correct parent/child nesting.
- Add a chaos/failure-simulation test proving the documented fallback actually triggers.

### Dependencies
Phase 4 (single-agent runtime, SSE trace streaming, and `agent_runs`/`agent_run_steps` this phase extends). Phase 2 (the `ProviderAdapter` and cost-accounting abstraction model-routing builds on). Phase 5 (memory v2's vector-DB infrastructure — **must not be missed**, since memory v2 cannot exist without Phase 5's vector-DB foundation, even though it uses a separate namespace).

### Required skills
`ai-architect`, `openai-agents-sdk-expert`, `openai-expert`, `vector-database-expert`, `opentelemetry-expert`, `redis-expert`, `system-designer`.

### Risks
- The single highest-risk mistake in this phase is letting agent memory v2 share a vector-DB namespace/collection with Phase 5's RAG knowledge-base store — even though both live in the same physical vector DB instance per Phase 0's ADR, cross-contamination between "what an agent remembers" and "what a document says" would corrupt both retrieval quality and grounding.
- A handoff contract that isn't genuinely typed/versioned (e.g., passing a raw transcript "just this once" for convenience) reintroduces the exact silent-context-mutation risk `CLAUDE.md` §4 explicitly rules out.
- A documented fallback that has never actually been exercised under simulated failure is not a real fallback — this must be tested via chaos injection, not assumed correct from code review alone.

### Acceptance criteria
- Given a supervisor-worker topology, when run, then each handoff carries a typed `handoff_contract` payload (summary + pointers), never a raw transcript.
- Given the primary model provider is simulated as unavailable, when a run requiring that model executes, then the documented fallback model/provider is used and the trace records why.
- Given agent memory v2 and Phase 5's knowledge base both exist in one workspace, when either is queried, then results never cross into the other's namespace.
- Given a multi-agent run, when viewed in the trace UI, then handoffs render with correct parent/child nesting over the same SSE transport used in Phase 4.

### Deliverables
`apps/api/orchestration-service/domain/topologies/`, `packages/contracts/handoff_contract.ts`, `apps/api/orchestration-service/application/model_routing.py`, `apps/api/orchestration-service/infrastructure/memory/session_memory_store.py`, extended trace-viewer components, `docs/adr/0007-multi-agent-topology-and-memory-v2.md`.

### Definition of Done
All 10 DoD items apply. DoD 2 (architecture) is a primary gate — the topology and memory-namespace-separation design is exactly the kind of scalability-sensitive design requiring a recorded `architecture-reviewer` verdict. DoD 6 (performance) covers multi-agent run latency/cost budgets, tracked separately from single-agent budgets. **Independently shippable** means: a user can configure a supervisor-worker or planner/executor/critic team, run it, watch live multi-agent handoff traces, and see a documented fallback actually trigger under a simulated provider failure — entirely built on top of, and never breaking, the Phase 4 single-agent feature already in production.

### Estimated implementation order
Position 9 of 12. Strictly follows Phase 4 — this is Macro Phase 2's entire content and is never pulled forward ahead of Phase 8's Macro-Phase-1 close.

---

## PHASE 10 — DAG Workflow Automation & Collaboration

**Maps to:** Macro Phase 3 (Workflow Automation & collaboration).

### Goal
Build a DAG-based workflow engine — conditional branching, human-in-the-loop approval nodes, workflow versioning — strictly as a layer invoking Phase 9's orchestration primitives, plus real-time multi-user canvas collaboration, the platform's first legitimate WebSocket use case.

### Business value
Workflow Automation targets Team-tier expansion and retention (`project-memory.md` §12 Phase 3 goal) by letting teams compose durable, reviewable, multi-step automations with a human checkpoint — a capability enterprise and team buyers explicitly need before they'll trust an agent with a consequential action (`CLAUDE.md` §4 Human Approval).

### Features
- `workflow`/`workflow_version`/`workflow_node`/`workflow_edge` schema, conditional branching, human-in-the-loop approval nodes as a first-class node type with durable pause/resume state.
- **Explicit architectural boundary**: a workflow node invokes an existing Phase 4 agent or Phase 9 topology — it never reimplements handoff/routing itself.
- Workflow versioning, parallel to Phase 8's prompt-versioning pattern (immutable versions, diffable, rollback-able).
- Richer collaboration/sharing: per-resource share links and co-editing, extending Phase 1's RBAC.
- Hybrid marketplace search extending Phase 8's marketplace catalog with Phase 5's vector infrastructure (semantic + keyword over listings).
- First legitimate WebSocket use case: real-time multi-user canvas collaboration — explicitly deferred until now per `decision-log.md` #20, not pulled earlier.

### User stories
- As a **Team-tier workspace admin**, I want to build a multi-step workflow with a human-approval node before a consequential action, so that nothing irreversible happens without a person in the loop.
- As two **teammates on the same workspace**, I want to co-edit a workflow canvas in real time, so that we can design together without stepping on each other's changes.
- As an **AI engineer**, I want a workflow node to invoke an existing agent/topology rather than redefine its logic, so that changes to the underlying agent automatically propagate to every workflow using it.

### Technical tasks
- Alembic migrations for `workflow`, `workflow_version`, `workflow_node`, `workflow_edge`, with an explicit foreign key from `workflow_node` to `agents`/topology configuration (never inlined logic).
- Implement the workflow execution engine `apps/api/orchestration-service/application/workflow_engine.py`, delegating every node execution to Phase 9's orchestration layer via a stable internal call — never re-implementing handoff/routing.
- Implement durable pause/resume for approval nodes: `apps/api/orchestration-service/infrastructure/workflow_pause_state.py` (Postgres-backed, survives worker restart).
- Implement WebSocket collaboration: `apps/api/orchestration-service/interface/routers/canvas_collab_ws.py` (token validated at handshake, teardown on disconnect).
- Extend RBAC for per-resource share links: `apps/api/auth-service/application/resource_sharing.py`.
- Extend marketplace search: `apps/api/integration-service/application/hybrid_marketplace_search.py`, reusing Phase 5's retrieval pipeline pattern.
- Build the workflow canvas and approval-node UI: `apps/web/app/(dashboard)/workflows/[workflowId]/builder/`.

### Dependencies
Phase 9 (workflow nodes invoke Phase 9's orchestration primitives — this is a hard, explicit architectural dependency, not incidental). Phase 8 (workflow versioning mirrors the prompt-versioning pattern established there). Phase 1 (RBAC extension for sharing). Phase 5 (marketplace search reuses the vector-DB retrieval pattern).

### Required skills
`ai-workflow-engineer`, `system-designer`, `fastapi-expert`, `react-expert`, `authorization-expert`, `vector-database-expert`.

### Risks
- The single biggest architectural risk in this phase is a workflow node quietly reimplementing routing/handoff logic instead of delegating to Phase 9 — this must be caught in `architecture-reviewer`, since it would fork orchestration logic into two divergent implementations.
- **Open design question, flagged not silently resolved**: whether WebSocket collaboration state is Redis-backed (recommended for multi-instance API servers, since AgentVerse's hot path runs at least two instances per `CLAUDE.md` §5) or held in-process (would not scale past one instance). This phase's implementer must resolve this explicitly before shipping, not default to the simpler in-process approach under time pressure.
- Durable pause/resume for approval nodes that isn't actually crash-safe (e.g., state held only in worker memory) would silently lose a workflow's progress on a worker restart — exactly the kind of gap that only surfaces during an incident, not a normal test run.

### Acceptance criteria
- Given a Team-tier workspace, when a user builds a multi-node workflow with a human-approval step, then the workflow pauses durably at that node and resumes correctly after approval, even across a worker restart.
- Given a workflow node invokes an agent, when that agent's underlying `agent_version` changes, then the workflow automatically uses the updated version without any workflow-level code change (proving no logic was forked).
- Given two teammates open the same workflow canvas, when both edit concurrently, then changes propagate to each other in real time over WebSocket, with no lost updates under a documented conflict-resolution rule.
- Given the marketplace search bar, when queried, then results blend semantic and keyword relevance over both first-party (Phase 8) and any listings that exist at this point.

### Deliverables
Migrations for `workflow`/`workflow_version`/`workflow_node`/`workflow_edge`, `apps/api/orchestration-service/application/workflow_engine.py`, `apps/api/orchestration-service/infrastructure/workflow_pause_state.py`, `apps/api/orchestration-service/interface/routers/canvas_collab_ws.py`, `apps/web/app/(dashboard)/workflows/[workflowId]/builder/`, `docs/adr/0008-workflow-engine-boundary.md` (recording the "never reimplement Phase 9" boundary and the WS state-storage decision).

### Definition of Done
All 10 DoD items apply. DoD 2 (architecture) is the primary gate — the workflow/orchestration boundary and the WS state-storage decision both require a recorded `architecture-reviewer` verdict before implementation proceeds. DoD 7 (accessibility) applies to the workflow canvas and approval-node UI, including the collaborative-editing affordances. **Independently shippable** means: a Team-tier workspace can build a multi-node DAG workflow with a human-in-the-loop approval step, two teammates can co-edit the canvas live, and the workflow correctly delegates every node's execution to Phase 9's orchestration layer — with zero forked orchestration logic.

### Estimated implementation order
Position 10 of 12. Strictly on top of Phase 9 — Macro Phase 3's entire content, never pulled forward.

---

## PHASE 11 — Growth Loops & Multi-Provider Breadth

**Maps to:** Macro Phase 4 (Growth loops & multi-provider breadth).

### Goal
Instrument and optimize referral/template-sharing growth loops on top of the marketplace, prove the provider-abstraction payoff by adding a second LLM provider with zero orchestration rewrite, open third-party template publishing under moderation, and dogfood AgentVerse's own runtime for internal support/onboarding automation.

### Business value
This phase directly targets Macro Phase 4's goal of acquisition efficiency and loop efficiency > 1 (`project-memory.md` §12), while also being the first real-world validation that Phase 2's abstraction layer was worth building — if adding Anthropic as a provider requires touching orchestration code, that is itself a finding that the abstraction failed its purpose.

### Features
- Referral/template-sharing growth loops with AARRR funnel instrumentation, built on Phase 8's marketplace and an event-tracking pipeline.
- A second LLM provider (e.g., Anthropic) added as a **new adapter implementing Phase 2's `ProviderAdapter` interface** — no runtime/orchestration rewrite required.
- Third-party template publishing: `marketplace_listing` schema extending Phase 8's first-party-only templates, with a moderation workflow reusing Phase 6's security-review path for any bundled tool/MCP config.
- Dogfooded internal automations (support-ticket triage, onboarding) built on AgentVerse's own agent runtime, running on Phase 3/4's worker+runtime infrastructure under normal workspace RBAC — no privilege bypass for "internal" use.

### User stories
- As a **growth/marketing stakeholder**, I want referral attribution to work end-to-end when a user shares a template, so that I can measure and optimize the acquisition loop.
- As an **AI engineer**, I want to switch my agent from OpenAI to a second provider with a config change, not a rewrite, so that I can validate the abstraction actually delivers swappability.
- As a **third-party template author**, I want my submitted template to pass a security review before it's listed, so that the marketplace stays trustworthy for installers.
- As an **internal support engineer**, I want ticket triage automated by an agent built on AgentVerse itself, so that the team validates the product by using it, per `CLAUDE.md` §2 AI First.

### Technical tasks
- Instrument AARRR events in `apps/web/lib/analytics/` and the corresponding ingestion pipeline in `apps/api/notification-service/` (or a dedicated analytics sink), with a single-source event taxonomy.
- Implement `apps/api/orchestration-service/infrastructure/providers/anthropic_adapter.py` implementing the existing `ProviderAdapter` port — no changes to `apps/api/orchestration-service/application/` or `domain/` orchestration code permitted as part of this task; any such need is itself a finding to report, not silently work around.
- Alembic migration for `marketplace_listing` (third-party, `status` enum including a moderation-pending state).
- Implement the moderation workflow `apps/api/integration-service/application/moderate_listing.py`, invoking Phase 6's existing tool/MCP security-review checks for any bundled configuration — never a new, separate review path.
- Build the internal support-triage agent using the standard builder (Phase 4) and workflow engine (Phase 10) — dogfooded, not special-cased infrastructure.

### Dependencies
Phase 8 (marketplace and first-party templates this phase extends to third-party). Phase 2 (the `ProviderAdapter` interface the second provider implements). Phase 6 (the security-review path moderation reuses). Phase 3/4 (the worker+runtime infrastructure internal dogfooding runs on).

### Required skills
`growth-engineer`, `analytics-engineer`, `openai-expert` (translated learnings), `mcp-expert`, `security-reviewer`, `ai-automation-engineer`.

### Risks
- If adding the Anthropic adapter turns out to require touching orchestration/business logic, that is a direct signal that Phase 2's abstraction design had a leak — this must be treated as a real finding and escalated, not quietly patched around inside the new adapter.
- A moderation workflow that re-implements its own ad hoc security checks instead of reusing Phase 6's existing review path creates two divergent security postures for tool/MCP configs — one for first-party-attached tools, one for marketplace-listed ones.
- Dogfooding internal automations under anything other than normal workspace RBAC (e.g., a special "internal" bypass) would both violate the "no privilege bypass" principle and mean the internal team isn't actually validating the same experience a customer gets.

### Acceptance criteria
- Given a user shares a template via a referral link, when a new user signs up through it, then referral attribution is recorded end-to-end and visible in the growth dashboard.
- Given an agent configured to use the new second provider, when it runs, then it executes successfully with zero changes to any orchestration/topology code — proving the abstraction's payoff.
- Given a third-party template submission with a bundled MCP tool, when it's reviewed, then it passes through the exact same security-review checks Phase 6 established, not a separate path.
- Given the internal support-triage agent, when it processes a real ticket, then it runs under the same RBAC and worker infrastructure as any customer workspace's agent.

### Deliverables
`apps/api/orchestration-service/infrastructure/providers/anthropic_adapter.py`, migration for `marketplace_listing`, `apps/api/integration-service/application/moderate_listing.py`, AARRR event-taxonomy documentation, the internal support-triage agent configuration (built via the standard product, not custom code).

### Definition of Done
All 10 DoD items apply. DoD 3 (security) is a primary gate for the moderation workflow specifically. DoD 6 (performance) covers the new provider's latency/cost profile compared against the documented routing table. **Independently shippable** means: referral attribution works measurably, an agent can switch LLM provider with zero runtime code changes, a third-party template passes security review before listing, and internal support triage runs live on AgentVerse's own platform under ordinary workspace RBAC.

### Estimated implementation order
Position 11 of 12.

---

## PHASE 12 — Open Marketplace, Enterprise Compliance & Own MCP Surface

**Maps to:** Macro Phase 5 (Full marketplace + enterprise compliance) — final phase.

### Goal
Take third-party publishing to a fully open, two-sided marketplace GA; expose AgentVerse's own agents/workflows as an MCP server surface for external consumption; and ship the enterprise compliance stack — SSO/SCIM, audit logs, dedicated resources, SOC 2 readiness, multi-region — closing the roadmap.

### Business value
This phase is where enterprise-led expansion and compliance-gated deals become possible (`project-memory.md` §12 Phase 5 goal) — SSO/SCIM, audit trails, and dedicated resources are the concrete, named blockers enterprise buyers have (`project-memory.md` §3 Enterprise Teams persona), and shipping AgentVerse's own MCP server last, only after years of consuming MCP correctly (Phase 6), is the trustworthy order to build a server surface others will depend on.

### Features
- Fully open two-sided marketplace: public listings, ratings/reviews, purchase/install flow — GA extension of Phase 11's third-party publishing.
- AgentVerse's own MCP server surface exposing agents/workflows to external MCP clients — built on Phase 6's MCP-**client** learnings but as a genuinely new **server**-side surface, correctly sequenced last, never conflated with tool-consumption work.
- SSO/SAML + SCIM provisioning, extending — never replacing — Phase 1's authentication.
- `audit_logs` (already created in Phase 1) extended to cover RBAC/billing/agent/workflow changes comprehensively, append-only, immutable.
- Dedicated worker-pool resources for Enterprise, extending Phase 3's worker infrastructure.
- SOC 2 readiness: control documentation mapped to concrete implemented mechanisms, not policy text alone.
- Multi-region deployment, extending Phase 0's infrastructure decisions.

### User stories
- As an **enterprise buyer**, I want to provision my organization via SSO/SCIM, so that user lifecycle is managed centrally through our identity provider, not manually.
- As an **enterprise compliance officer**, I want a complete, immutable audit trail of every RBAC, billing, agent, and workflow change, so that I can satisfy an external audit.
- As an **external developer**, I want to connect my own MCP client to AgentVerse's exposed agents, so that I can integrate AgentVerse capabilities into my own tooling.
- As an **enterprise buyer**, I want dedicated worker resources and a documented multi-region posture, so that my workloads are isolated from noisy-neighbor risk and regional data residency requirements.

### Technical tasks
- Extend `marketplace_listing` toward GA: ratings/reviews schema, purchase/install flow in `apps/web/app/(marketplace)/`.
- Implement AgentVerse's own MCP server: `apps/api/integration-service/interface/mcp_server/`, exposing a controlled, workspace-scoped subset of agents/workflows as MCP tools/resources — a new server-side surface, explicitly not a reuse of the Phase 6 client code.
- Implement SSO/SAML + SCIM: `apps/api/auth-service/infrastructure/sso/{saml_provider,scim_provisioning}.py`, extending the Phase 1 auth adapter rather than replacing it.
- Extend `audit_logs` write points across every sensitive enforcement point (RBAC grants/denials, billing state changes, agent/workflow publish/delete) — append-only, no UPDATE/DELETE grant for the application role.
- Provision dedicated worker-pool resources via `infra/` IaC, extending Phase 3's worker containerization with resource-tier isolation.
- Author SOC 2 control-mapping documentation in `docs/compliance/soc2-control-mapping.md`, each control citing the concrete code/infra mechanism that satisfies it.
- Extend `infra/` for multi-region topology (managed data-store replication, region-aware routing).

### Dependencies
Phase 11 (third-party publishing this phase takes to GA). Phase 6 (MCP-consuming learnings this phase's own-server implementation is built on, as a new surface, not a shared one). Phase 1 (auth this phase extends with SSO/SCIM; `audit_logs` table already exists from Phase 1). Phase 3 (worker infrastructure this phase adds dedicated-tier resourcing to). Phase 0 (infra/IaC foundation this phase extends for multi-region).

### Required skills
`security-engineer`, `authentication-expert`, `authorization-expert`, `mcp-expert`, `cloud-architect`, `infrastructure-engineer`, `database-architect`.

### Risks
- Conflating AgentVerse's new MCP **server** surface with the existing Phase 6 MCP **client** code (e.g., reusing client-side assumptions about trust direction) would invert the threat model — the server surface must be designed from first principles as "external, untrusted callers reaching into AgentVerse," not as an extension of "AgentVerse calling out to trusted-ish external tools."
- SOC 2 documentation written as policy prose disconnected from actual implemented controls is worse than no documentation — it creates false audit confidence; every control must cite a real, checkable mechanism.
- Multi-region deployment introduces data-residency and replication-lag questions that interact with `workspace_id` tenant isolation (Rule 11) in new ways (e.g., which region owns a given workspace's system-of-record row) — this must be resolved architecturally, not left implicit.

### Acceptance criteria
- Given an enterprise workspace configured with SSO/SCIM, when a user is provisioned or deprovisioned in the identity provider, then their AgentVerse access updates accordingly without manual intervention.
- Given any RBAC grant/denial, billing change, or agent/workflow publish/delete, when it occurs, then it is written to the immutable `audit_logs` table from the enforcement point itself.
- Given an external MCP client connects to AgentVerse's own MCP server, when it lists available tools, then only the workspace-scoped subset the connecting credential is authorized for is exposed.
- Given the SOC 2 control-mapping document, when reviewed, then every control cites a concrete, verifiable implementation, not policy text alone.
- Given dedicated Enterprise worker resources, when a non-Enterprise workspace's run load spikes, then Enterprise workloads are unaffected (resource isolation holds).

### Deliverables
GA marketplace UI extensions, `apps/api/integration-service/interface/mcp_server/`, `apps/api/auth-service/infrastructure/sso/`, extended `audit_logs` write points across services, dedicated-tier worker IaC in `infra/`, `docs/compliance/soc2-control-mapping.md`, multi-region IaC extensions, `docs/adr/0009-own-mcp-server-surface.md`, `docs/adr/0010-multi-region-topology.md`.

### Definition of Done
All 10 DoD items apply, at the platform's highest bar. DoD 3 (security) and DoD 2 (architecture) are joint primary gates — this phase carries the platform's largest new external-facing trust surface (the MCP server) and its most consequential infrastructure change (multi-region). DoD 5 (documentation) is heavily weighted given the SOC 2 compliance-mapping deliverable. **Independently shippable** means: an enterprise customer can provision via SSO/SCIM, see complete audit trails, run on dedicated resources across regions, and optionally integrate via AgentVerse's own MCP server — the full enterprise-compliance and open-marketplace promise of Macro Phase 5, delivered as the roadmap's final phase.

### Estimated implementation order
Position 12 of 12. Final phase — Macro Phase 5's entire content, correctly sequenced last so the own-MCP-server surface is built only after the platform has years of MCP-consuming discipline (Phase 6) behind it.

---

## Council Review

### (a) Duplicated work flags — intentional layering, not actual duplication

- **Cost accounting** spans Phase 2 (the `cost_accounting.py` primitive) → Phase 4 (displayed in the trace viewer) → Phase 7 (aggregated into durable `billing_usage_events`). Phase 7 must **consume**, not recompute, the primitive; any file that independently calculates cost outside `cost_accounting.py` is a DRY violation (`CLAUDE.md` Rule 3), not a legitimate second implementation.
- **Vector DB usage** spans Phase 5 (RAG/knowledge-base retrieval) → Phase 9 (agent memory v2) → Phase 10 (hybrid marketplace search). This is one physical vector DB instance per Phase 0's ADR, with three logically separate namespaces/collections — not three separate infrastructure decisions. Phase 9's memory store must never share a namespace with Phase 5's KB store.
- **SSE vs. WebSockets** has one firm, documented boundary: SSE (Phase 4, extended in Phase 9) is server-to-client run/trace streaming; WebSockets (first legitimate use in Phase 10) is bidirectional collaborative editing, and — per `decision-log.md` #20 — the future home of interrupt/steer-a-running-agent controls. No phase should reach for WebSockets where SSE already suffices.
- **The 2026-10-01 re-validation checkpoint** (decision-log entries #7 OpenAI, #9 Agents SDK, #10 MCP, #14 Monorepo, #17 CQRS) spans Phase 2's ADR (re-affirming #7/#9/#10) and Phase 6's MCP work (which inherits #10's checkpoint) and Phase 0's ADR (#14/#17). This is **one checkpoint event** on that date, reviewing all five decisions together against real evidence accumulated by then — not five separate re-review efforts scattered across phases.

### (b) Dependency conflicts

No dependency conflicts require reordering. Two things are worth calling out explicitly so they are never missed:
- Phase 9's agent memory v2 has a real, non-optional dependency on Phase 5 (the vector-DB infrastructure) even though memory v2 is conceptually a Macro-Phase-2 capability and Phase 5 is Macro-Phase-1 — this is by design (infrastructure built early, feature built later) and is listed explicitly in Phase 9's Dependencies field.
- Phase 7 (billing) depends on both Phase 1 (workspace) and Phase 4 (usage/cost data source) — satisfied by construction since both precede it in sequence.
- Phase 10's WebSocket state-storage question (Redis-backed vs. in-process) is flagged as a **latent open design gap**, not a hard conflict — it is explicitly left for that phase's implementer to resolve via `architecture-reviewer` sign-off before shipping, rather than silently defaulted.

### (c) Ordering optimization opportunities

- **Phase 2 ↔ Phase 3**: no dependency on each other; both depend only on Phase 0 and both gate exclusively into Phase 4. This is a real, actionable parallelization opportunity — two engineers/pods can build the provider abstraction and the worker/queue infrastructure concurrently, compressing calendar time before they converge at Phase 4.
- **Phase 5 ↔ Phase 6**: no hard mutual dependency; both depend only on Phase 4. The current sequential order (5 then 6) is fine and is what this document specifies, but if resourcing allows, they could be parallelized the same way as Phase 2/3 — noted here as an option, not a requirement.
- **Phase 8** could in principle split into two phases (eval harness alone; marketplace starter templates alone). It is deliberately kept combined to hit the 13-phase target *and* because both halves share the same hard constraint — neither may ship user-facing prompt/template exposure until the eval-gate exists — making them one coherent unit of "safe to expose to a brand-new user," not two.

### (d) Full macro-phase coverage confirmation

- **Macro Phase 1 (MVP foundation)** is fully covered by Phases 0–8, with nothing missing: repo/infra bootstrap, workspace/auth/RBAC, provider abstraction, worker/queue infrastructure, single-agent builder/runtime/SSE, knowledge bases/RAG, tool-calling/MCP-consuming, billing/Stripe, and prompt versioning/eval/marketplace starter templates. Nothing from Macro Phase 2 or later (multi-agent topologies, DAG workflows, growth loops, third-party marketplace, enterprise compliance) appears anywhere in Phases 0–8.
- **Macro Phase 2 (Depth of orchestration)** is fully covered by Phase 9 alone, strictly following Phase 4 — multi-agent topologies, typed handoff contracts, model routing with fallbacks, and agent memory v2 are all present and nowhere pulled forward into Phases 0–8.
- **Macro Phase 3 (Workflow Automation & collaboration)** is fully covered by Phase 10 alone, strictly built on top of Phase 9 — DAG workflows, human-in-the-loop approval, workflow versioning, richer collaboration/sharing, hybrid marketplace search, and the first WebSocket use case are all present and correctly sequenced after orchestration depth exists.
- **Macro Phase 4 (Growth loops & multi-provider breadth)** is fully covered by Phase 11 — referral/template-sharing growth loops, a second LLM provider behind the existing abstraction, third-party template publishing with moderation, and dogfooded internal automations.
- **Macro Phase 5 (Full marketplace + enterprise compliance)** is fully covered by Phase 12, the roadmap's final phase — open two-sided marketplace GA, AgentVerse's own MCP server surface (correctly placed last and never conflated with Phase 6's MCP-consuming work), SSO/SCIM, audit logs, dedicated resources, SOC 2 readiness, and multi-region deployment.

**Net result:** all five macro-phases and every one of their named sub-capabilities are accounted for exactly once, in strict dependency order, with no forward-pulled capability anywhere in the sequence.

### Final self-audit

- **Phase count.** Exactly 13 phases exist, numbered Phase 0 through Phase 12 inclusive — confirmed by the 13 `## PHASE N` headings in this document, one per phase, in strictly ascending order.
- **Macro-phase ordering.** Strict ordering holds throughout: no Macro-Phase-2-or-later capability (multi-agent orchestration, DAG workflows, growth loops, third-party/open marketplace, enterprise compliance, own MCP server) appears before Phase 9. Phases 0–8 contain only Macro-Phase-1 content.
- **Dependencies.** Every phase's Dependencies field references exclusively lower-numbered phases: Phase 0 (none), Phase 1 → 0, Phase 2 → 0, Phase 3 → 0, Phase 4 → 1/2/3, Phase 5 → 4, Phase 6 → 4, Phase 7 → 1/4, Phase 8 → 4/5/6, Phase 9 → 4/2/5, Phase 10 → 9/8/1/5, Phase 11 → 8/2/6/3/4, Phase 12 → 11/6/1/3/0. No forward reference exists anywhere.
- **Required skills.** Every skill name cited across all 13 phases was checked against the actual `.claude/skills/` directory listing loaded at the start of this task (80 entries: `agentverse-master-ai-engineering-team` plus 79 role skills). All citations — including `ai-workflow-engineer`, `ai-automation-engineer`, `openai-agents-sdk-expert`, `stripe-integration-expert`, `saas-strategist`, `linux-expert`, `cloud-architect`, and every other reference — are confirmed exact matches to real folder names; none were invented.

---

*This roadmap is a planning decomposition, not a new authority. On any apparent conflict with `CLAUDE.md`, `project-memory.md`, or `decision-log.md`, those documents govern and `agentverse-master-ai-engineering-team` is the final arbiter, per `CLAUDE.md` preamble and `ai-playbook.md` §16.*
