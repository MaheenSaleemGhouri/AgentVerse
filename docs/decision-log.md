# AgentVerse — Engineering Decision Log

*The permanent record of why AgentVerse is built the way it is.*

This log records the **reasoning, alternatives, and trade-offs** behind AgentVerse's foundational technology and architecture decisions. It complements — never restates — the [Engineering Constitution](../CLAUDE.md) (`CLAUDE.md`), which is the highest authority and defines the *standards* for using each of these choices. The *facts* ("what we use") live in [`project-memory.md`](./project-memory.md) §6 Tech Stack; this log owns the *why*. The two must never drift.

Each entry follows a fixed structure: **Decision · Status · Reason · Alternatives Considered · Trade-offs · Owner Skill · Review Date · Current Version**. Every decision states real downsides — a decision with no trade-offs is not credible. All initial entries are **Accepted / v1.0**. Superseding a decision follows the process in [`ai-playbook.md`](./ai-playbook.md) → Continuous Improvement Process (Status → `Superseded`, new entry links back).

This log is the standing record; per-change decisions still go through the ADR process in `CLAUDE.md` §5/§13 (`docs/adr/NNNN-title.md`). ADRs are point-in-time; this log is the durable index of the load-bearing ones.

---

## 1. Why Next.js

- **Decision.** Next.js 15 (App Router) + React 19 as the frontend framework for `apps/web`.
- **Status.** Accepted.
- **Reason.** AgentVerse has three distinct rendering needs in one app: a heavily interactive builder canvas (client-driven), streaming execution traces (streaming SSR shell around a client stream consumer), and cached, SEO-relevant public/marketplace pages. App Router serves all three with Server Components by default, Suspense streaming, and ISR — without adopting three tools (`nextjs-expert`; `CLAUDE.md` §6).
- **Alternatives Considered.** A pure SPA (Vite + React Router): rejected — no first-class SSR/SEO for the marketplace, and no server-component boundary discipline. Remix: viable but smaller ecosystem for our shadcn/ui + Vercel path. SvelteKit: rejected — the team and component ecosystem are React-centric.
- **Trade-offs.** App Router's Server/Client boundary model has real learning-curve cost and easy-to-get-wrong `'use client'` sprawl (a documented common mistake). Caching semantics are subtle and stale-data bugs are easy. Tighter coupling to Vercel's deployment model for best results. We accept these for the rendering flexibility.
- **Owner Skill.** `nextjs-expert` (App Router), under `senior-frontend-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 2. Why FastAPI

- **Decision.** FastAPI + async Python for all backend services (`apps/api`) and workers.
- **Status.** Accepted.
- **Reason.** The backend is I/O-bound and streaming-heavy: concurrent long-running agent runs, SSE/WebSocket trace streaming, and many concurrent LLM/tool calls. FastAPI's async-first model, Pydantic v2 validation, and generated OpenAPI (which feeds `packages/contracts`) fit this precisely and keep the frontend's types generated, not hand-written (`fastapi-expert`; `CLAUDE.md` §7, §5).
- **Alternatives Considered.** Django + DRF: rejected — sync-first, heavier, ORM-centric; async streaming is awkward. Node/NestJS: viable and shares the TS ecosystem, but Python is the lingua franca of the AI/LLM tooling (OpenAI SDK, Agents SDK, embedding/eval libraries). Go: excellent concurrency but a poorer AI-library ecosystem and slower iteration for this domain.
- **Trade-offs.** Python async is easy to misuse — a single blocking call in an `async def` stalls the event loop (hence `CLAUDE.md` Rule 12). CPU-bound work (tokenization, embedding batching) must be explicitly offloaded. Python's runtime performance is below Go/Rust; we compensate with async I/O and background workers.
- **Owner Skill.** `fastapi-expert`, `python-expert`, under `senior-backend-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 3. Why PostgreSQL

- **Decision.** PostgreSQL as the single system of record for all durable relational data.
- **Status.** Accepted.
- **Reason.** AgentVerse's core data is relational and correctness-critical: workspaces, members/roles, agents, versions, runs, run steps, tool calls, knowledge bases, billing. It needs transactions (billing to the cent), strong isolation levels for concurrent usage aggregation, partitioning for high-volume tables (`agent_run_steps`, `tool_calls`, `billing_usage_events`), and — via pgvector — an optional path to keep vectors close to their metadata (`database-architect`, `postgresql-expert`; `CLAUDE.md` §8).
- **Alternatives Considered.** MySQL: viable but weaker on partitioning, JSONB, and extension ecosystem (pgvector). MongoDB: rejected — billing and tenancy demand ACID transactions and joins, not document flexibility. A managed proprietary DB (DynamoDB/Spanner): rejected for MVP — lock-in and modeling friction for a relational domain; "boring, proven technology" wins (`CLAUDE.md` §3 KISS).
- **Trade-offs.** Vertical-scaling ceiling and operational care (PgBouncer pooling, autovacuum tuning on high-churn tables, partition management from day one) are on us. Horizontal write scaling is harder than in a distributed store; we mitigate with read replicas and partitioning, and accept the ceiling for the foreseeable horizon.
- **Owner Skill.** `database-architect` (schema), `postgresql-expert` (runtime/perf).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 4. Why Redis

- **Decision.** Redis as the in-memory layer: cache, session store, background job queue (Streams), distributed locks, and rate-limit counters — never the system of record.
- **Status.** Accepted.
- **Reason.** Concurrent agent execution needs a fast coordination layer: a durable-enough job queue between `apps/api` and `apps/worker` (Redis Streams with consumer groups give at-least-once delivery, `XACK`, `XPENDING` for stuck-job detection), distributed locks to stop duplicate runs, per-workspace sliding-window rate limiting, and hot-path caching of agent configs/membership (`redis-expert`, `system-designer`; `CLAUDE.md` §8).
- **Alternatives Considered.** A dedicated broker (RabbitMQ/Kafka) for the queue: rejected for MVP — operational weight beyond need; Streams cover our delivery/DLQ requirements. Postgres-as-queue (`SELECT ... FOR UPDATE SKIP LOCKED`): viable and one fewer moving part, but couples queue throughput to the primary DB and lacks Redis's rate-limit/lock primitives. Memcached: rejected — no streams, no persistence, no data structures.
- **Trade-offs.** Redis is not durable by default — everything in it must be reconstructable from Postgres or safely losable (`CLAUDE.md` Rule 13). Misuse is easy: locks without TTLs, Pub/Sub used as a queue (no delivery guarantee), `KEYS *` blocking the single thread, unbounded memory. These are guarded by standards but remain sharp edges.
- **Owner Skill.** `redis-expert`, with `system-designer` for queue/HA topology.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 5. Why Vector Database

- **Decision.** A Vector Database (pgvector in the existing Postgres, or a managed vector DB) as the semantic layer for knowledge-base RAG and marketplace search — never the source of truth.
- **Status.** Accepted.
- **Reason.** Agents answer from per-workspace knowledge bases (RAG) and users find templates via semantic search — both require ANN similarity over embeddings with tenant-isolated filtering. HNSW indexes give the query-latency/recall balance KB retrieval needs; hybrid semantic+keyword ranking serves marketplace discovery (`vector-database-expert`, `rag-expert`; `CLAUDE.md` §8, §9).
- **Alternatives Considered.** pgvector vs. a dedicated managed vector DB (Pinecone/Weaviate/Qdrant): starting with pgvector keeps vectors beside their relational metadata (one datastore, one tenancy model, simpler ops); a managed vector DB is the escalation path for scale or a dedicated Enterprise namespace, deferred until a concrete need. Keyword-only search (Postgres FTS): rejected — misses semantic recall. Embeddings-in-Redis: rejected — not a durable, indexed semantic store.
- **Trade-offs.** pgvector shares resources with the transactional workload and has scaling limits versus purpose-built vector stores. Correctness is fragile: every query must pre-filter by `workspace_id` (post-filtering an unscoped top-k both leaks tenant data and degrades recall), and mixing embedding-model versions in one search produces meaningless scores. Re-embedding on a model upgrade is a managed backfill + cutover, not an in-place rewrite. Infrastructure choice (pgvector vs. managed) escalates to `principal-software-architect`.
- **Owner Skill.** `vector-database-expert` (storage/indexing), `rag-expert` (retrieval pipeline).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 6. Why Docker

- **Decision.** Docker (multi-stage images, non-root, pinned bases) for every service, with `docker-compose` for the full local stack.
- **Status.** Accepted.
- **Reason.** AgentVerse is a multi-service system (frontend, FastAPI services, worker fleet, Postgres, Redis, vector DB). Docker gives dev/staging/prod parity (twelve-factor), reproducible artifacts promoted unchanged staging → production, and a one-command local stack with health-check-gated startup (`docker-expert`, `devops-engineer`; `CLAUDE.md` §12).
- **Alternatives Considered.** Running services bare on VMs: rejected — no parity, painful onboarding. Nix: powerful reproducibility but a steep team learning curve versus need. Buildpacks (as the primary build): viable on some platforms but less control over multi-stage optimization and non-root hardening.
- **Trade-offs.** Image-size and build-time discipline is ongoing work; a careless Dockerfile leaks secrets into layers or ships a build toolchain to production. Local resource use for the full compose stack is non-trivial. We accept these for parity and reproducibility.
- **Owner Skill.** `docker-expert`, under `devops-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 7. Why OpenAI

- **Decision.** OpenAI as the first LLM/embedding provider, integrated **behind** AgentVerse's provider-abstraction layer.
- **Status.** Accepted.
- **Reason.** OpenAI offers the capability breadth AgentVerse's runtime needs today — strong models across the cost/quality spectrum for routing, native JSON-schema/structured outputs, function/tool calling, streaming, and embeddings — with a mature async SDK. Crucially it enters through the abstraction, so no orchestration/route/workflow code imports the SDK directly and a second provider never touches business logic (`openai-expert`, `ai-architect`; `CLAUDE.md` §9, Rule 16).
- **Alternatives Considered.** Anthropic/Google/open models as the *first* provider: all viable and expected as future providers behind the same abstraction; OpenAI is first for structured-output and tool-calling maturity plus the Agents SDK path (decision 9). A hard single-provider commitment with no abstraction: explicitly rejected — provider lock-in is an existential risk flagged by `startup-advisor`.
- **Trade-offs.** Provider concentration risk (pricing, rate limits, outages, policy) — mitigated by the abstraction and a documented fallback per routing rule (`CLAUDE.md` §9 Fallback strategy). Provider-specific error taxonomy must be translated at the boundary. Cost management (token accounting per workspace/run) is mandatory, not optional.
- **Owner Skill.** `openai-expert`, with `ai-architect` co-owning the abstraction contract.
- **Review Date.** 2026-10-01.
- **Current Version.** v1.0.

---

## 8. Why Claude Code

- **Decision.** Claude Code as the engineering org's build tool for building AgentVerse itself.
- **Status.** Accepted.
- **Reason.** AgentVerse is built by an AI-assisted team under strict standards. Claude Code supports the disciplines the constitution demands: planning mode before large/risky changes, subagent delegation for genuinely independent work, self-review against the owning skill's checklist, and maintenance of this 80-skill library — making AI-assisted output as reliable as the standards it is held to (`claude-code-expert`; `CLAUDE.md` §9 Claude Code, §18).
- **Alternatives Considered.** Unstructured LLM chat assistance: rejected — no planning/delegation/self-review discipline, no skill library. Traditional IDE autocomplete only: insufficient for multi-file, cross-cutting work. This is a build-process choice, distinct from AgentVerse's own agent runtime.
- **Trade-offs.** Requires discipline to avoid failure modes (coding without a stated plan, delegating tightly-coupled work to subagents, skipping self-review) — the standards exist precisely because the tool makes those mistakes cheap to make. Destructive actions require explicit confirmation (`CLAUDE.md` Rule 20).
- **Owner Skill.** `claude-code-expert`, under `agentverse-master-ai-engineering-team`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 9. Why OpenAI Agents SDK

- **Decision.** Build the agent runtime, where SDK-based, on the OpenAI Agents SDK — realizing topologies designed by `ai-architect` in its `Agent`/`Tool`/`handoff`/`Guardrail`/`Session` primitives.
- **Status.** Accepted.
- **Reason.** The SDK provides production-shaped primitives for exactly what AgentVerse's runtime needs — agent/tool definitions, handoffs, guardrails, session memory, and native tracing — that map onto the agent-builder data model, avoiding a bespoke reimplementation of tool-loop/handoff plumbing (`openai-agents-sdk-expert`; `CLAUDE.md` §9 Agents SDK runtime).
- **Alternatives Considered.** A hand-rolled orchestration loop on raw Chat Completions: maximal control but reinvents guardrails, sessions, handoffs, and tracing. LangGraph/CrewAI/AutoGen: viable orchestration frameworks, but these are named competitors' foundations and add a heavier abstraction we would need to bend to AgentVerse's trace schema and tool boundary. The SDK keeps us close to the provider we already use (decision 7) while `ai-architect` keeps topology design SDK-independent.
- **Trade-offs.** A fast-moving SDK with frequent breaking changes to core primitives — the version is pinned and upgrades reviewed against the changelog (`CLAUDE.md` §9). Coupling risk: SDK trace formats must be translated into AgentVerse's own trace-event schema so the UI never depends on SDK internals, and every SDK tool call must still route through AgentVerse's tool-execution boundary. `ai-architect` owns designs; this SDK only implements them.
- **Owner Skill.** `openai-agents-sdk-expert`, implementing `ai-architect`'s designs.
- **Review Date.** 2026-10-01.
- **Current Version.** v1.0.

---

## 10. Why MCP

- **Decision.** Model Context Protocol (MCP) as the standard for connecting agents to external tools (and, later, for exposing AgentVerse's own tool surface).
- **Status.** Accepted.
- **Reason.** MCP is an open, growing standard for tool/resource integration, letting AgentVerse users connect agents to third-party systems (databases, SaaS APIs, internal tools) without a bespoke connector per integration. Workspace-scoped, credential-isolated connections with schema-validated tools map cleanly into the agent builder's tool-discovery UX (`mcp-expert`; `CLAUDE.md` §4 MCP, §9 MCP).
- **Alternatives Considered.** Bespoke per-integration connectors: rejected — unbounded maintenance, no discovery standard. OpenAI function-calling only (no external protocol): rejected — every third-party tool would need custom wiring; MCP gives a common discovery/transport model. Waiting for the ecosystem to mature: rejected — early standardization is a positioning advantage for the marketplace/integrations pillars.
- **Trade-offs.** An evolving standard with churn risk. Security surface is significant: tool descriptions are effectively part of the prompt (vague descriptions degrade tool selection), tool results are untrusted external content (injection vector identical to RAG chunks), transport must match trust boundary (stdio only for co-located/trusted, SSE/HTTP for remote), and a hung server must be time-boxed so it can't stall a run. Every MCP call still routes through the central tool-execution boundary.
- **Owner Skill.** `mcp-expert`, coordinating with `ai-architect`/`openai-agents-sdk-expert`/`security-engineer`.
- **Review Date.** 2026-10-01.
- **Current Version.** v1.0.

---

## 11. Why Tailwind CSS

- **Decision.** Tailwind CSS v4 with CSS-first `@theme` token configuration as the styling system.
- **Status.** Accepted.
- **Reason.** AgentVerse needs one coherent design-token system (color/spacing/radius/shadow/typography/motion) spanning a dense canvas, dashboards, and a marketing-adjacent marketplace, with co-equal dark/light theming. Tailwind v4's CSS-first `@theme` variables give a single source of truth referenced everywhere, pairs natively with shadcn/ui, and keeps styling colocated with markup (`tailwind-css-expert`, `design-system-architect`; `CLAUDE.md` §6, §15).
- **Alternatives Considered.** CSS Modules / plain CSS: rejected — no shared token enforcement, easy drift. CSS-in-JS (styled-components/Emotion): rejected — runtime cost, poorer RSC/streaming fit, weaker token discipline. Vanilla Extract: viable typed tokens but smaller ecosystem and no shadcn/ui synergy.
- **Trade-offs.** Utility-class verbosity and markup noise; a real risk of token-system erosion via arbitrary values (`w-[137px]`, raw hex) that requires periodic audits to catch. The `@theme` layering (primitive → semantic → component) must be governed or it sprawls. We accept these for single-source theming.
- **Owner Skill.** `tailwind-css-expert` (implementation), `design-system-architect` (token system).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 12. Why shadcn/ui

- **Decision.** shadcn/ui as the component-primitive foundation, composed into AgentVerse product components.
- **Status.** Accepted.
- **Reason.** shadcn/ui gives accessible, unstyled-by-default primitives (Card, Sheet, Dialog, DropdownMenu, Table) that we own in-repo and theme through our Tailwind tokens — composed into product components (`AgentCard`, run trace viewer, usage meter) without re-implementing focus trapping or ARIA. Copy-in ownership avoids version-lock on an external component library (`shadcn-ui-expert`, `design-system-architect`; `CLAUDE.md` §6, §15).
- **Alternatives Considered.** MUI/Ant/Chakra: rejected — opinionated visual language fighting our Linear/Stripe register, heavier runtime, harder deep customization. Fully bespoke components: rejected — reinventing accessible primitives is expensive and error-prone (a documented anti-pattern). Radix alone: shadcn/ui already builds on Radix and adds the themed, CLI-managed layer we want.
- **Trade-offs.** Copy-in components become our maintenance burden — upstream fixes aren't automatic, so we keep customization thin (theme via variables, don't fork source) to stay mergeable. Variant governance (`cva`) must be disciplined to avoid single-use variant sprawl. We accept ownership cost for control and accessibility inheritance.
- **Owner Skill.** `shadcn-ui-expert`, under `design-system-architect`/`senior-frontend-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 13. Why TypeScript

- **Decision.** TypeScript in strict mode (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`) across the frontend.
- **Status.** Accepted.
- **Reason.** AgentVerse's frontend consumes complex, multi-state contracts — run status, subscription status, typed SSE/WebSocket event unions — where illegal states must be unrepresentable and a new backend event type must fail the build until handled. Strict TS plus generated OpenAPI types (never hand-written) makes misuse a compile error, not a runtime bug (`typescript-expert`; `CLAUDE.md` §6 TypeScript, §5 API contracts).
- **Alternatives Considered.** JavaScript + JSDoc: rejected — no enforced strictness, weak refactoring safety at this contract complexity. Loose (non-strict) TypeScript: rejected — `any` erodes the exact guarantees (discriminated unions, exhaustive event handling) we depend on. ReScript/Elm: rejected — ecosystem and hiring friction against React/shadcn.
- **Trade-offs.** Strict mode has real friction — more upfront typing, occasional fights with `exactOptionalPropertyTypes`, and generated-type regeneration discipline. `any` is banned; `unknown` + narrowing/Zod is the only external-boundary escape hatch. We accept the friction for compile-time safety.
- **Owner Skill.** `typescript-expert`, under `senior-frontend-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 14. Why Monorepo

- **Decision.** A single monorepo (`apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `infra/`) for the platform.
- **Status.** Accepted.
- **Reason.** The frontend, backend, and workers share one release cadence and a single contract surface (`packages/contracts`, generated from FastAPI's OpenAPI). A monorepo keeps generated types, shared logic, and atomic cross-cutting changes coherent, avoiding cross-repo version skew between the API and its consumers (`principal-software-architect`, `git-expert`; `CLAUDE.md` §5, §14).
- **Alternatives Considered.** Polyrepo (one repo per service): the constitution's *default* for independently deployable services, chosen against here because our services currently share a release cadence and deploy unit — `git-expert` mandates recording and revisiting this. As service boundaries and cadences diverge (esp. the worker fleet at scale), a split is the expected evolution.
- **Trade-offs.** A monorepo risks accidental coupling (a service importing another's internals) that must be actively prevented (`CLAUDE.md` §5, §16 — no cross-service internal imports; shared logic only via versioned internal packages). CI must build/test/deploy services independently despite one repo. Larger checkout and broader CODEOWNERS surface. We accept these while cadences align, and treat the boundary decision as revisitable, not permanent.
- **Owner Skill.** `principal-software-architect`, with `git-expert`/`github-expert`.
- **Review Date.** 2026-10-01.
- **Current Version.** v1.0.

---

## 15. Why Clean Architecture

- **Decision.** Clean-architecture layering inside every backend service: `domain/` → `application/` → `infrastructure/` → `interface/`, dependencies pointing inward.
- **Status.** Accepted.
- **Reason.** AgentVerse must swap external dependencies (LLM providers, Stripe, auth provider, MCP servers) without touching core logic, and keep business rules (routing, proration, permission checks) framework-free and unit-testable without I/O. Inward-pointing dependencies with vendor SDKs behind adapters deliver exactly that (`principal-software-architect`, `fastapi-expert`; `CLAUDE.md` §3, §5).
- **Alternatives Considered.** Framework-centric layout (fat routers/"active record" everywhere): rejected — couples business logic to FastAPI and vendor SDKs, making provider swaps and testing painful. Hexagonal/ports-and-adapters: essentially the same intent under a different name; we adopt the layered vocabulary the constitution already fixes.
- **Trade-offs.** More upfront structure and indirection (mapping between layers, defining ports) than throwing logic in a route handler — overkill if applied dogmatically to trivial CRUD. The discipline is enforced by review; the payoff is provider-swappability and testability. We keep layering real but avoid ceremony where a thin handler → service call suffices.
- **Owner Skill.** `principal-software-architect`, with `senior-backend-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 16. Why Event-Driven Architecture

- **Decision.** Asynchronous, event-driven communication (Redis Streams/pub-sub) as the default between services; synchronous REST only for tight-latency request-time needs.
- **Status.** Accepted.
- **Reason.** Agent-run lifecycle events (`run.started`, `run.step.completed`, `run.completed`, `run.failed`) have multiple independent consumers — billing usage aggregation, SSE trace streaming, trace archival — best served by one write and many decoupled readers. Making the orchestration path wait synchronously on billing/notification writes would add latency and false dependencies to the critical path (`microservices-architect`, `system-designer`; `CLAUDE.md` §5).
- **Alternatives Considered.** Synchronous REST everywhere: rejected — chatty call chains, cascading failures, orchestration blocked on non-critical writes (a distributed-monolith symptom). A dedicated event bus (Kafka): deferred — operationally heavier than needed for MVP volumes; Redis Streams give versioned, schema-validated events with consumer groups and DLQs today, with Kafka as a scale escalation.
- **Trade-offs.** Eventual consistency: consumers see events after the fact, so anything needing an immediate answer (a plan-limit check before starting a run) stays synchronous with a timeout/fallback. Event payloads must be versioned (`event_type`, `schema_version`) or a producer change silently breaks consumers. Debugging async flows requires end-to-end trace correlation. Redis streams are trimmed/archived, never treated as permanent storage.
- **Owner Skill.** `microservices-architect` (boundaries/contracts), `system-designer` (queue mechanics).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 17. Why CQRS

- **Decision.** CQRS is **not** adopted as a platform-wide pattern. AgentVerse applies only a lightweight, targeted read/write separation where it already earns its place: a durable append-only write path (`billing_usage_events`) with a separate fast read path (Redis usage counters for the in-product Usage panel), and read replicas / a low-priority pool for heavy analytical reads.
- **Status.** Accepted.
- **Reason.** The skill library does not establish full CQRS (separate command/query models with distinct stores and projections). Forcing it would violate "build only what the current task needs" (`CLAUDE.md` §16, Rule 10). The one place a read/write split is genuinely warranted — real-time usage display vs. durable billing truth — is already handled: Redis counters serve the UI, durable events serve billing, reconciled nightly (`saas-strategist`, `redis-expert`; `CLAUDE.md` §8). Analytical reads use replicas, not the transactional pool (`postgresql-expert`; `CLAUDE.md` §8, §17).
- **Alternatives Considered.** Full CQRS + event sourcing across the platform: rejected — speculative complexity, extra stores and projection lag, no current requirement demands it. No separation at all (bill from the live Redis counter): rejected — violates `CLAUDE.md` Rule 13 (Redis is never the system of record) and risks incorrect billing.
- **Trade-offs.** The targeted split means two representations of usage (fast/approximate vs. durable/authoritative) that must be reconciled — accepted, because that reconciliation is exactly the correctness guarantee we want. Choosing *not* to generalize CQRS means if a future high-scale read model genuinely needs it, that will be a new decision with its own ADR, not an existing capability to lean on.
- **Owner Skill.** `system-designer`/`principal-software-architect` (pattern scope); `saas-strategist`/`billing-expert` + `redis-expert`/`postgresql-expert` (the specific usage split).
- **Review Date.** 2026-10-01.
- **Current Version.** v1.0.

---

## 18. Why Background Workers

- **Decision.** All long-running agent execution runs in dedicated background workers (`apps/worker`) on a Redis-backed queue, never inline in an API request.
- **Status.** Accepted.
- **Reason.** Agent runs are long-running and bursty (multi-step reasoning loops, tool calls, LLM latency). Executing them inline would time out requests and block the event loop under load. Workers let run-triggering endpoints return `202 Accepted` + a `run_id`/poll URL immediately, scale horizontally on queue depth, and recover a crashed run by re-picking the job (`system-designer`, `fastapi-expert`; `CLAUDE.md` §5, §7, Rule 14).
- **Alternatives Considered.** Inline execution in the request handler: explicitly rejected (`CLAUDE.md` Rule 5, Rule 14) — request timeouts, no isolation, no recovery. FastAPI `BackgroundTasks` for runs: rejected — fine for sub-second fire-and-forget only, no durability/retry/visibility for something that can fail expensively. A serverless function per run: viable but complicates long-lived streaming, connection reuse, and per-workspace concurrency fairness.
- **Trade-offs.** A distributed system's full weight: every worker task must be idempotent (at-least-once delivery, redelivery must not double-execute or double-bill), every queue needs a DLQ and bounded retry, and workers must hold no unrecoverable in-memory state. Per-workspace concurrency caps are needed to prevent noisy-neighbor starvation. More moving parts than an inline call — accepted as the cost of production reliability.
- **Owner Skill.** `system-designer`, with `senior-backend-engineer`/`redis-expert`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 19. Why SSE

- **Decision.** Server-Sent Events (SSE) as the default transport for streaming live execution traces/logs from backend to browser.
- **Status.** Accepted.
- **Reason.** The execution-trace stream is inherently one-directional server→client (step started, token, tool call, step completed, run completed). SSE fits this exactly: it runs over plain HTTP, auto-reconnects, supports `Last-Event-ID`-style resume so a client reconnecting mid-run doesn't lose history, and is simpler to operate and proxy than WebSockets. FastAPI serves it via `StreamingResponse` reading from Redis pub/sub, and a client leaf consumes it inside a server-rendered shell (`fastapi-expert`, `system-designer`, `nextjs-expert`; `CLAUDE.md` §5, §6).
- **Alternatives Considered.** WebSockets for trace streaming: rejected as the default — full-duplex is unnecessary for a server-push stream and adds connection-management and scaling complexity (see decision 20 for where WS *is* warranted). Long-polling: rejected — higher latency and overhead, no native resume. gRPC streaming: rejected — poor browser fit without a proxy layer.
- **Trade-offs.** SSE is one-directional (no client→server messages on the same channel) and browsers cap concurrent SSE connections per origin over HTTP/1.1 (mitigated by HTTP/2). Streaming endpoints must clean up their Redis subscription on client disconnect or leak connections under load (a documented review-gate item). The full trace must be durably stored (Postgres/object storage), not held only in memory, so resume works.
- **Owner Skill.** `fastapi-expert` (endpoint), `system-designer` (fan-out/resume), `nextjs-expert` (client consumption).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 20. Why WebSockets

- **Decision.** WebSockets reserved for genuinely bidirectional, low-latency interactions (e.g., interactive/collaborative canvas sessions, interrupt/steer-a-running-agent controls) — not used where one-directional SSE suffices.
- **Status.** Accepted.
- **Reason.** Some surfaces need real client→server messaging with low latency: sending a control message to a running agent (pause/cancel/inject input), or future multi-user canvas collaboration. WebSockets provide full-duplex for those cases; the transport is chosen per interaction rather than defaulting everything to one mechanism (`system-designer`, `fastapi-expert`; `CLAUDE.md` §5, §6).
- **Alternatives Considered.** WebSockets for *everything* including trace streaming: rejected — over-engineered for server-push (decision 19). SSE + separate POST requests for the rare client→server control action: viable and used where interaction is infrequent; WS is chosen only when sustained low-latency bidirectionality is the actual requirement. Polling for control state: rejected — latency and overhead.
- **Trade-offs.** WebSockets are more complex to authenticate (token validated during handshake before `accept()`), scale (sticky sessions/fan-out), and operate (proxy/load-balancer drain on deploy) than SSE. A dropped connection needs explicit reconnect/resume handling, and a disconnect must tear down its Redis subscription/background task so it can't leak into another session (a security-review-gate item). We accept this only where bidirectionality is real.
- **Owner Skill.** `system-designer` (topology), `fastapi-expert` (handshake/auth/cleanup).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 21. Why Stripe

- **Decision.** Stripe (Checkout, Billing Portal, webhooks) as the payment and subscription-billing provider.
- **Status.** Accepted.
- **Reason.** AgentVerse needs subscriptions (Free/Pro/Team/Enterprise), usage-based overage, self-serve plan changes, and dunning, while keeping card data entirely off our servers. Stripe-hosted Checkout/Elements/Billing Portal keep AgentVerse in the smallest PCI scope (SAQ A), and webhooks feed verified subscription/invoice facts into `billing_subscriptions` (`stripe-integration-expert`, `billing-expert`; `CLAUDE.md` §8 Money, Rule 15).
- **Alternatives Considered.** Building payment/card handling in-house: rejected — enormous PCI burden and risk for zero differentiation. Paddle/Lemon Squeezy (merchant-of-record): viable for tax handling but less flexible for usage-based metering and enterprise invoicing at our intended depth. Braintree/Adyen: heavier integration, weaker self-serve subscription tooling than Stripe for our stage.
- **Trade-offs.** Provider dependency and fees. Webhook handling is subtle and must be exactly-once by construction (Stripe guarantees at-least-once): signature verification on the raw body, event-ID idempotency recorded atomically with the state change, out-of-order delivery handled by object state not arrival order, and slow work queued not done in the handler. `billing_subscriptions` is a synchronized projection of Stripe's truth and must be reconciled to catch missed webhooks. Subscription state logic stays in `billing-expert`, never duplicated in the webhook handler.
- **Owner Skill.** `stripe-integration-expert` (Stripe plumbing), `billing-expert` (internal billing logic).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 22. Why RBAC

- **Decision.** Workspace-scoped role-based access control — `owner > admin > member > viewer`, deny-by-default — enforced server-side via a single shared permission-check dependency, with API-key scopes as the intersection of key tier and role.
- **Status.** Accepted.
- **Reason.** AgentVerse is multi-tenant with clear organizational roles per workspace; a strict role hierarchy plus resource-level permissions (view/edit/run/delete/share) is the right granularity and is simple to reason about. Centralizing the check in one dependency means a route that "forgot" the check is a pattern bug, not a scattered oversight, and workspace scoping is enforced at the same layer (`authorization-expert`, `security-engineer`; `CLAUDE.md` §7, §10, Rule 6, Rule 11).
- **Alternatives Considered.** Full ABAC (attribute-based) or a policy engine (OPA/Cedar): rejected for now — more power than the current role model needs, added operational complexity; the deferred escalation path if fine-grained/attribute policies become a real requirement. Per-route ad hoc `if role ==` checks: explicitly rejected — unenforceable, drift-prone, and a documented anti-pattern. Frontend-only gating: rejected — never an enforcement point (`CLAUDE.md` §10).
- **Trade-offs.** A fixed role hierarchy is less expressive than attribute policies — complex sharing/delegation scenarios layer resource-level overrides on top of roles, and edge cases may eventually strain the model (the ABAC review trigger). Getting the `403` (same-workspace permission gap) vs. `404` (cross-workspace, don't leak existence) semantics right is subtle and must be tested cross-role and cross-workspace on every protected route.
- **Owner Skill.** `authorization-expert`, under `security-engineer`.
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 23. Why Workspace Isolation

- **Decision.** The workspace is the absolute tenant/isolation boundary: every tenant-owned table, query, cache key, vector search, and event carries and filters by `workspace_id`, resolved from the authenticated identity — never from client input.
- **Status.** Accepted.
- **Reason.** A multi-tenant AI platform handling customers' knowledge bases, agent configs, and run logs cannot risk cross-tenant leakage. A single, uniform `workspace_id` scoping invariant across Postgres, Redis, the vector store, and the event stream makes isolation checkable and testable everywhere, and cross-workspace access is denied without leaking existence (`database-architect`, `authorization-expert`, `vector-database-expert`, `security-engineer`; `CLAUDE.md` §8, §10, Rule 11).
- **Alternatives Considered.** Database-per-tenant (physical isolation): rejected for the general case — operationally unscalable across many small workspaces; reserved as the *Enterprise* escalation (dedicated Vector DB namespace / dedicated resources). Row-level security (Postgres RLS) as the sole mechanism: viable as defense-in-depth but not relied on alone — application-layer scoping via the shared dependency is the primary, testable enforcement point. Schema-per-tenant: rejected — migration and connection sprawl.
- **Trade-offs.** Shared-table multi-tenancy puts the full weight of isolation on disciplined scoping — a single missing `workspace_id` filter is a cross-tenant leak, so it is a hard merge-blocking invariant with mandatory cross-tenant tests. Composite indexes must lead with `workspace_id`; vector queries must pre-filter (not post-filter) by it. Noisy-neighbor effects are managed at the app layer (per-workspace concurrency caps, rate limits) rather than by physical isolation until Enterprise.
- **Owner Skill.** `database-architect` (schema), `authorization-expert` (enforcement), `security-engineer` (invariant authority).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 24. Why Observability

- **Decision.** Observability as a launch requirement, built on three separate pillars correlated by shared IDs: distributed tracing (OpenTelemetry, one trace per run), metrics (RED/USE), and structured logging — plus per-run cost and agent-execution as a first-class dashboard/alert surface.
- **Status.** Accepted.
- **Reason.** Observability *is* a product differentiator for AgentVerse (the moat is orchestration + memory + observability) and an operational necessity: an agent run spans API → orchestration → worker → tool call → LLM call, and without one connected trace with correct parent/child nesting you cannot answer "why did this run fail and what did it cost." OpenTelemetry propagates trace context across every async/queue boundary; the three pillars stay separate and correlate via `request_id`/`workspace_id`/`run_id` (`observability-engineer`, `opentelemetry-expert`, `logging-expert`; `CLAUDE.md` §1, §4, §12, Rule 18).
- **Alternatives Considered.** Logs-only (grep the logs): rejected — cannot reconstruct a distributed run's causal tree or per-step cost. A single merged "observability" blob: rejected — the constitution keeps metrics/logs/traces as distinct pillars, correlated not merged. Observability as a post-launch follow-up: explicitly rejected — it is a launch requirement and a Definition-of-Done item (`CLAUDE.md` §12, §19).
- **Trade-offs.** Instrumentation cost and discipline: trace context must be explicitly propagated across every async boundary (dropping it is a bug, not an acceptable gap), and agent-run logs may contain PII so they are redacted in general logs with full content only in a restricted, shorter-retention stream. Telemetry volume/cost and retention must be managed. We accept this because observability is both product and operations.
- **Owner Skill.** `observability-engineer` (strategy/metrics), `opentelemetry-expert` (tracing), `logging-expert` (logs).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

## 25. Why AI Evaluation & Prompt Versioning

*(Covers the constitution's paired requirements: "Why AI Evaluation" and "Why Prompt Versioning" — a single decision because in AgentVerse they are one discipline: a prompt is not shippable without an eval.)*

- **Decision.** Every prompt (internal product prompts and user-authored agent-builder templates) is a **versioned artifact** with a golden dataset and passing **eval** results; no prompt ships or changes without an eval run, and AI output is evaluated by structure/behavior, never exact text match.
- **Status.** Accepted.
- **Reason.** LLM output is non-deterministic; "it looked good in one manual test" is not evidence, and an unversioned prompt cannot be rolled back or regression-checked. Versioning makes prompts diffable and independently deployable; the eval harness (golden datasets, deterministic checks first, reference-anchored LLM-as-judge only where needed, cost/latency tracked per variant) catches quality regressions before production and on every target-model change. This is what makes AgentVerse's AI *reliable and improvable* rather than hand-tuned (`prompt-engineer`, `ai-architect`, `rag-expert`, `testing-architect`; `CLAUDE.md` §4, §9, §11).
- **Alternatives Considered.** Inline prompt string literals edited in place: explicitly rejected — no history, no rollback, no regression gate (a documented anti-pattern). Exact-match / text-similarity assertions on LLM output in the fast test suite: rejected — reintroduces flakiness the strategy exists to prevent; structural/behavioral assertions live in pytest, quality judgment lives in the eval harness, and the two are never conflated. Manual QA only: rejected — not repeatable or regression-safe.
- **Trade-offs.** Real upfront and ongoing cost: building/maintaining golden datasets (with adversarial, out-of-scope, and ambiguous cases), running evals in CI (adding time and token spend), and validating each prompt against its *fallback* model as well as its primary. LLM-as-judge must be reference-anchored or its scores drift. Few-shot examples are added only when they earn measured lift, since they cost tokens/latency. We accept this cost because unevaluated prompt changes are silent quality regressions waiting to ship.
- **Owner Skill.** `prompt-engineer` (prompt versioning + eval harness), with `testing-architect` (AI-output test strategy), `rag-expert` (retrieval metrics), `ai-architect` (routing/fallback).
- **Review Date.** 2027-01-01.
- **Current Version.** v1.0.

---

*This log is maintained through [`ai-playbook.md`](./ai-playbook.md) → Continuous Improvement Process. A decision is never edited to reverse it; its Status becomes `Superseded` and a new entry links back (mirroring the ADR immutability rule, `CLAUDE.md` §13). On any conflict with `CLAUDE.md`, the constitution and the Master skill decide.*
