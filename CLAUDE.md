# AgentVerse Engineering Constitution

This is the permanent engineering constitution for AgentVerse — the enterprise SaaS platform for building, deploying, and orchestrating AI agents and multi-agent systems. Every plan, implementation, review, and AI-assisted collaboration in this repository is bound by this document.

It was synthesized from the 80-skill Claude Code skill library at `/mnt/c/AgentVerse/.claude/skills/`: one Master skill (`agentverse-master-ai-engineering-team`) plus 79 specialist role skills. It is not a summary of those files — it is the organization's single, reconciled source of truth, written so that a rule appears once even when many skills touch it, with a citation to the skill(s) that own the underlying domain.

**Final authority.** When two rules, standards, or ownership claims conflict — here or in any future work — the Master skill `agentverse-master-ai-engineering-team` and its Operating Principles are the final arbiter. Any conflict is resolved in favor of the Master's principles, and where a rule in this constitution reflects such a resolution it says so explicitly. Individual specialist skills own the depth of their domain; the Master owns coherence across domains.

**How to read a citation.** A rule tagged `(database-architect)` means that skill owns the standard; this constitution enforces it uniformly. A rule tagged with several skills is a genuinely cross-cutting invariant unified here so it is stated once.

**The stack, fixed.** Frontend: Next.js 15 (App Router) + React 19 + TypeScript (strict) + Tailwind CSS v4 + shadcn/ui + Framer Motion. Backend: FastAPI + async Python across services (auth/workspace, orchestration/control-plane, billing, agent-runtime workers, integration/tool-gateway, notification). Data: PostgreSQL (system of record) + Redis (cache/queue/coordination) + a Vector Database (semantic layer). Monorepo: `apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `infra/`.

**The domain vocabulary, fixed.** Workspace (the tenant/isolation root), agent, agent version, run, run step, tool call, trace, knowledge base, MCP connection, agent-builder canvas, streaming execution logs, marketplace template, subscription tier (Free/Pro/Team/Enterprise), usage quota. Product pillars: Agent Builder, Orchestration, Observability, Marketplace, Platform (billing/workspaces/RBAC).

---

## 1. Vision

**Mission.** AgentVerse exists to make building, running, and operating reliable multi-agent AI systems as approachable, observable, and trustworthy as deploying to Vercel or paying with Stripe. A developer should be able to design an agent on a canvas, connect it to real tools over MCP, run it, watch every step stream live, understand exactly what it cost and why it succeeded or failed, and ship it to production — without assembling that stack themselves.

**Long-term vision.** The category-defining platform for agent orchestration, distinguished not by wrapping a single model in a chat box but by depth of orchestration (planner/executor/critic, supervisor-worker, DAG workflows with human-in-the-loop) and depth of observability (one connected trace per run across orchestration, tool calls, and LLM calls, with per-run cost). This is the moat: orchestration + agent memory + observability, grounded in what actually ships, never in buzzword inflation (`startup-advisor`, `ai-architect`).

**Core philosophy.** We are one engineering organization, not a collection of contractors. Every discipline — product, architecture, backend, frontend, AI, data, security, DevOps, testing, design, docs, growth — operates as facets of a single coherent team whose output reads as one aligned recommendation, never a committee transcript (`agentverse-master-ai-engineering-team`). We move from idea to production through discipline (requirements → design → implementation → tests → review → deploy readiness), we build only what the current task needs, and we treat tests, security, and reversibility as non-negotiable defaults rather than afterthoughts.

**Product purpose.** Serve three audiences with genuinely different needs from one product: individual builders (Free/Pro, self-serve, DX- and price-sensitive), teams (Team tier, collaboration and observability), and enterprises (Enterprise tier, SSO, audit logs, dedicated resources, compliance) — without letting one audience's needs degrade another's experience (`product-manager`, `marketing-strategist`).

**Definition of success.** Success is measured by whether a workspace reaches a first successful agent run quickly (activation, `product-manager`'s canonical metric: a `run_completed` within 24h of workspace creation), keeps running agents over time (retention), expands (seats and usage), and trusts the platform enough to run it in production (reliability, observability, correct billing to the cent). Vanity totals (raw signups) are never success; instrumented activation, retention, expansion, run success rate, and net revenue retention are (`product-manager`, `saas-strategist`, `growth-engineer`, `business-intelligence-expert`).

---

## 2. Product Principles

These seven principles govern what we build and why, grounded in `product-manager`, `startup-advisor`, `saas-strategist`, and `business-analyst`.

**User First.** Every roadmap item names a persona (builder / workspace admin / enterprise buyer), a concrete system surface it touches, and a metric it moves; if it cannot name all three, it is not ready (`product-manager`). "Looks good" is never a spec — features ship against owned, testable acceptance criteria written in Given/When/Then against real UI/API surfaces (`product-manager`, `qa-engineer`). Flows are designed for how a developer actually thinks about the task — define → connect → test → debug → deploy — not as a generic consumer wizard (`ux-designer`).

**AI First.** AgentVerse's core unit of work is an agent run, and the product is designed around it: orchestration topologies, live execution traces, tool calling, agent memory, and evaluation are first-class product surfaces, not add-ons (`ai-architect`, `ai-workflow-engineer`). We dogfood — internal operations (support triage, onboarding) are automated by building real agents on AgentVerse itself, because if our own team struggles to build something with the product, a customer will too (`ai-automation-engineer`).

**Simplicity.** MVP means one sharply cut use case, never "a smaller version of everything" (`product-manager`). The agent builder shows simple defaults first (a single prompt node) and reveals advanced configuration (tool schemas, retries, memory, guardrails) only when the user reaches for it — progressive disclosure (`ux-designer`). Pricing stays at four tiers; more tiers add decision friction without proportional conversion (`saas-pricing-expert`).

**Reliability.** Agents run in production; correctness is not optional. Every reasoning loop and workflow is bounded (max steps, cost, wall-clock), every run is idempotent against retry, and the platform degrades gracefully under load rather than falling over (`ai-architect`, `system-designer`, `redis-expert`). Billing is correct to the cent, reconciled against durable events (`billing-expert`, `saas-strategist`).

**Transparency.** System state is always legible: during a streaming run the user can always answer "what is happening right now, and is it working?" (`ux-designer`). Grounded agent answers carry citations traceable to source documents (`rag-expert`). Usage and cost are shown in-product against quota, never a surprise on the invoice (`saas-strategist`). Pricing is published, including exact usage-overage rates (`saas-pricing-expert`). Every factual claim in marketing copy is verifiable against the shipped product (`copywriting-expert`, `marketing-strategist`).

**Enterprise Quality.** Visual and interaction quality is a product feature, in the register of Linear, Stripe, Vercel, and Notion — restrained, information-dense without clutter, equally polished in dark and light theme (`senior-ui-designer`). WCAG 2.2 AA is the floor for every surface (`accessibility-expert`). Enterprise concerns — SSO, audit logs, tenant isolation, SLAs — are architected in, not bolted on (`authentication-expert`, `security-engineer`, `authorization-expert`).

**Long-term Thinking.** We build for requirements that exist today plus one known horizon — no speculative abstractions, no hypothetical future-proofing, no half-finished scaffolding (`agentverse-master-ai-engineering-team`, `principal-software-architect`). Public API contracts are promises to every customer integration; breaking one without a version bump and deprecation window is treated as an incident, not a refactor (`api-designer`). Pricing changes always ship with a grandfathering/migration plan (`product-manager`).

---

## 3. Engineering Principles

These are applied, not recited. Each states how AgentVerse engineers use it concretely.

**Clean Architecture.** Every backend service is layered: `domain/` (entities, zero framework imports) → `application/` (use cases/services) → `infrastructure/` (Postgres, Redis, vector DB, LLM clients) → `interface/` (FastAPI routers, schemas). Dependencies point inward; a route handler is thin orchestration that delegates to a service, and no LLM/agent logic lives in a router (`principal-software-architect`, `fastapi-expert`). The frontend mirrors this: business logic (validation, derived calculations, run-state transitions) lives in `lib/`/`hooks/`, never inline in JSX (`senior-frontend-engineer`).

**SOLID.** Concretely: every external dependency (LLM provider, Stripe, auth provider, MCP server) sits behind an internal adapter interface, so the core never imports a vendor SDK directly and providers are swappable (`solution-architect`, `openai-expert`, `ai-architect`) — dependency inversion in practice. Each service owns one bounded capability (single responsibility at the service level; `microservices-architect`). New behavior extends via composition and configuration, not by editing shared primitives to add conditionals (`design-system-architect`, `shadcn-ui-expert`).

**DRY.** Logic shared between a FastAPI service and a worker lives in an internal shared package, imported by both, never copy-pasted (`python-expert`). A design value (a color, a spacing unit) is defined exactly once as a token and referenced everywhere; duplication is a defect (`design-system-architect`). Event definitions, prompt templates, pricing configuration, and API error codes each have a single source of truth (`analytics-engineer`, `prompt-engineer`, `saas-pricing-expert`, `api-designer`). DRY never justifies coupling two services through a shared database — see Separation of Concerns.

**KISS.** Default to the simplest orchestration topology (single agent with tools) and escalate only when the task genuinely needs decomposition or verification (`ai-architect`). Prefer boring, proven technology (Postgres, Redis, FastAPI, Next.js) over novel tools absent a concrete constraint (`principal-software-architect`). The simplest fix that closes the gap to budget wins over an exotic one (`optimization-expert`).

**Composition over Inheritance.** Product UI components are composed from shadcn/ui primitives (`AgentCard` from `Card` + `Badge` + `Avatar` + `DropdownMenu`), never bespoke divs that re-implement focus trapping or ARIA (`shadcn-ui-expert`). Reasoning-loop primitives (tool-use loop, reflection, retry-with-backoff) are reusable functions composed per agent, not reinvented per agent type (`ai-architect`).

**Separation of Concerns.** Every entity has exactly one owning service; every other service reaches it through that service's API or an event, never a direct cross-schema join (`microservices-architect`, `principal-software-architect`, `database-architect`). Server state (TanStack Query) and client/UI state (Zustand) are never mixed in the same store (`senior-frontend-engineer`). The observability pillars are separate: metrics/strategy (`observability-engineer`), logs (`logging-expert`), traces (`opentelemetry-expert`), correlated by shared IDs, not merged.

**Modular Design.** Frontend feature code is colocated by route segment under `app/`, each feature owning its components, hooks, API client, and types with no cross-feature deep imports (`senior-frontend-engineer`, `principal-software-architect`). The retrieval pipeline is a distinct testable module (rewrite → retrieve → rerank → assemble), not inlined into orchestration (`rag-expert`).

**Reusability.** Before writing new logic, locate where equivalent logic already lives (`python-expert`). Prefer reusing the customer-facing workflow feature over a bespoke internal pipeline (`ai-automation-engineer`). A design-system variant must justify itself against at least two real consuming surfaces (`design-system-architect`).

**Scalability.** Long-running work is never inline in a request — it is dispatched to a worker and streamed back (`system-designer`, `senior-backend-engineer`). High-volume tables (`agent_run_steps`, `tool_calls`, `billing_usage_events`) are partitioned by `created_at` from their first production migration, not retrofitted (`postgresql-expert`). Worker fleets scale on queue depth, not CPU alone (`cloud-architect`, `system-designer`).

**Maintainability.** The execution path (request → service → worker → LLM/tool call) is traceable by reading directory names, not by tribal knowledge (`python-expert`). Every architectural decision of consequence is an ADR (`principal-software-architect`). Documentation lives in the repo, changes in the same PR as the code it describes (`documentation-engineer`).

**Testability.** Model choices, routing decisions, chunking, proration, and permission checks are written as pure functions so they can be unit-tested without I/O (`ai-architect`, `vector-database-expert`, `billing-expert`, `authorization-expert`). Dependency-injected clients (DB, Redis, LLM) are mockable via shared fakes (`fastapi-expert`, `python-expert`, `pytest-expert`).

**Readability.** Types are documentation — a well-typed signature makes misuse a compile error, not a runtime bug (`typescript-expert`). Dead code, unused imports, and commented-out blocks are removed on sight (`python-expert`). Commit messages explain why; the diff shows what (`git-expert`).

---

## 4. AI Engineering Principles

AgentVerse is an AI platform; these principles are load-bearing product rules, owned by `ai-architect`, `prompt-engineer`, `rag-expert`, `mcp-expert`, `openai-agents-sdk-expert`, and `openai-expert`.

**Agents.** An agent is stored, versioned configuration (system prompt, tools, knowledge base, model) authored in the builder and translated to a runtime `Agent` at execution time — never hand-authored outside the builder data model, or runtime behavior drifts from what the user configured (`openai-agents-sdk-expert`).

**Multi-Agent Collaboration.** Supported topologies are explicit: single-agent-with-tools, supervisor-worker, planner/executor/critic, sequential handoff. Topology follows the task; the simplest sufficient one is the default (`ai-architect`). Every agent-to-agent handoff carries a typed, versioned payload (a summary plus pointers like a run/trace ID, not a raw transcript dump) — an agent never silently mutates another's context (`ai-architect`).

**Prompt Engineering.** A prompt is a versioned artifact with a golden dataset and passing eval results, never a string literal buried in code; no prompt ships or changes without an eval run (`prompt-engineer`). Few-shot examples are added only when they earn measured lift on the eval set.

**Context Engineering.** Retrieved context is assembled within the target model's actual token budget (accounting for system prompt, history, and reserved output), ordered by relevance, and formatted with the shared delimiter conventions — never a flat top-k regardless of budget (`rag-expert`, `prompt-engineer`).

**Tool Calling.** Every tool call — native, MCP-sourced, or knowledge-base retrieval — routes through AgentVerse's central tool-execution boundary for logging, auth, and rate-limiting; nothing bypasses it, including SDK-wrapped tools (`mcp-expert`, `openai-agents-sdk-expert`). Tool-call arguments returned by the model are untrusted input, validated against the tool's schema before execution (`openai-expert`).

**MCP.** MCP connections are workspace-scoped and credential-isolated; credentials resolve from the secrets manager at call time, never stored in agent config or logged. Tool descriptions are treated as part of the prompt — a vague description degrades tool selection as much as a bad system prompt (`mcp-expert`).

**Memory.** Session memory persistence matches the actual conversation/run lifecycle and is backed by Redis/Postgres appropriately — never left on an SDK in-memory default in a multi-instance deployment, which loses state on a follow-up handled by a different instance (`openai-agents-sdk-expert`, `redis-expert`).

**Guardrails.** Guardrails are configuration derived from each agent's declared scope, versioned with the agent, and fail closed — a blocked input/output stops the run with a clear trace reason, never silent retry or ignore (`openai-agents-sdk-expert`, `security-engineer`).

**Retrieval.** Retrieval is a pipeline (query rewrite → hybrid semantic+keyword retrieve → rerank → assemble), and each stage earns its place only by measured improvement on a labeled eval set. Storage mechanics (embeddings, indexing, HNSW) are owned by `vector-database-expert`; pipeline behavior by `rag-expert`.

**Evaluation.** AI output is evaluated by structure and behavior (valid schema, correct tool-call shape, groundedness, cost/latency bounds), never by exact text match. Prompt-quality judgment routes to `prompt-engineer`'s eval harness; retrieval quality to `rag-expert`'s recall@k/precision@k/groundedness metrics; the fast test suite asserts structure only (`testing-architect`, `pytest-expert`).

**Human Approval.** Workflows support human-in-the-loop approval steps as a first-class node type with durable pause/resume state (`ai-workflow-engineer`). Any agent action with real-world side effects (sending email, calling a paid API, writing externally) requires an allow/deny policy check independent of the model's judgment (`security-engineer`). Internal automations touching customer-facing output default to draft-and-review (`ai-automation-engineer`).

**Cost Optimization.** Model routing is a deliberate cost/quality/latency decision per task type — cheap/fast models for classification and tool-selection, the strongest model reserved for final synthesis — documented in a routing table, never one hardcoded model for everything (`ai-architect`, `openai-expert`). Every LLM call records token usage attributed to workspace and run.

**Reliability.** Every reasoning loop and multi-agent workflow has an enforced step, cost, and time ceiling; a loop under the step limit can still be a cost incident, so all three bounds are required (`ai-architect`). Every model-routing rule has a documented fallback so one provider outage degrades gracefully (`openai-expert`).

**Observability.** Every orchestration step emits a trace event consumable by the execution-trace UI; if a step can't be represented in the trace UI, the design isn't finished (`ai-architect`).

**Tracing.** One connected trace per agent run spans API → orchestration → worker → tool call → LLM call, with correct parent/child nesting; trace context is explicitly propagated across every async/queue boundary, and dropping it is a bug, not an acceptable gap (`opentelemetry-expert`).

---

## 5. Software Architecture Standards

Owned by `principal-software-architect` (system-wide), `solution-architect` (feature-level), `system-designer` (distributed mechanics), and `microservices-architect` (service boundaries).

**Monorepo layout.** `apps/web` (Next.js 15), `apps/api` (FastAPI), `apps/worker` (background runners), `packages/contracts` (shared OpenAPI/TS types), `infra/` (Docker, IaC). Each independently deployable service ships its own `Dockerfile`, `.env.example`, and `README.md` documenting its owned datastore(s), public contract, and dependencies (`principal-software-architect`, `git-expert`).

**Service boundaries.** Bounded contexts, named for their capability: `auth`/`workspace`, `orchestration` (control plane — decides what happens next for a run), the `agent-runtime` worker fleet (executes run steps), `billing`, `integration`/tool-gateway, `notification`. A boundary is justified only by a real independent scaling, ownership, or failure-isolation need — never org-chart preference or "it felt cleaner." A capability stays inside an existing service until a concrete pain demands a split (`microservices-architect`, `senior-backend-engineer`).

**Dependency direction.** Inside a service, dependencies point inward (interface → application → domain; infrastructure implements domain ports). Across services, no service accesses another's database or schema directly — cross-service data goes through that service's API or a published event (`principal-software-architect`, `microservices-architect`, `database-architect`).

**Per-service data ownership.** Exactly one service owns each entity's source-of-truth table. The frontend never talks to `orchestration` or the worker fleet directly — all client traffic goes through the public `/api/v1` gateway; internal services are not internet-routable. Vector DB access is encapsulated behind the `agent-runtime` fleet; no other service queries the vector store directly (`principal-software-architect`).

**API contracts.** Single versioned public API under `/api/v1`, OpenAPI-first, owned by `api-designer` and generated into `packages/contracts` — the frontend never hand-writes API types (`typescript-expert`, `principal-software-architect`). SSE/WebSocket event schemas are documented as JSON Schema alongside REST contracts.

**Inter-service communication.** Asynchronous (Redis streams/pub-sub) by default; synchronous REST only for request-time needs with a tight latency budget. Every synchronous inter-service call has an explicit timeout and a defined fallback/circuit-breaker — no unbounded waits, and no synchronous call chain nested more than two levels deep (`microservices-architect`, `system-designer`). Event payloads are versioned and schema-validated with an explicit `event_type` and `schema_version` (`microservices-architect`).

**Shared libraries.** Logic reused across services/workers lives in a versioned internal package imported by both, never a shared runtime dependency on another service's codebase, never copy-paste (`python-expert`, `git-expert`).

**Feature modules & naming.** Services: `<domain>-service` (kebab-case). Python modules: snake_case. TypeScript: PascalCase components, camelCase utilities/hooks. Queues: `<domain>.<event>`. One Postgres schema per service, named for the service (`principal-software-architect`).

**Scalability rules.** Long-running agent execution is always a background worker job, never inline in a request. Every queue has a dead-letter queue and a bounded retry policy with exponential backoff. Every stateless hot-path component runs at least two instances; no single point of failure in the request-serving path. Backpressure (429 + retry-after) is applied at the gateway before it cascades into worker/DB overload (`system-designer`).

**Architecture decisions.** Every new service, new datastore, cross-service dependency, or scalability-sensitive feature requires an ADR (Context/Decision/Consequences/Alternatives, in `docs/adr/NNNN-title.md`) reviewed and signed off by `architecture-reviewer` before implementation starts. New services define `/health` and `/ready` before any business route (`principal-software-architect`, `architecture-reviewer`).

---

## 6. Frontend Standards

Owned by `senior-frontend-engineer` (architecture and code-review authority), with `nextjs-expert`, `react-expert`, `typescript-expert`, `tailwind-css-expert`, `shadcn-ui-expert`, and `framer-motion-expert` as specialists.

**Next.js 15 (App Router).** Server Components are the default for every route; every `'use client'` boundary is minimal and justified by a real need for state, effects, or browser APIs. On the builder canvas, only the canvas/node/edge interaction layer is client-rendered while surrounding chrome stays server-rendered. Initial data is server-fetched and passed as props; client-side refetch/mutation goes through TanStack Query hitting `lib/api/` (`nextjs-expert`, `senior-frontend-engineer`). Middleware stays thin — auth/redirect only, never business logic or data fetching. Marketplace and public pages are cached and SEO-optimized (ISR); authenticated dashboard/builder pages are never cached across users.

**React 19.** Streaming state is encapsulated in custom hooks (e.g., `useAgentRunStream(runId)`) with a clear return contract. High-frequency data (streaming log entries, canvas drag deltas) is isolated so re-renders don't cascade; streamed events are buffered/throttled and flushed on an interval, never `setState` per event. Subscription hooks (SSE, WebSocket, observers) always clean up on unmount — a leaked connection when navigating away from a trace view is a defect (`react-expert`). Components select the minimal Zustand/context slice, never the whole store.

**TypeScript (strict).** `strict: true` plus `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`; none disabled without an ADR. Multi-state concepts (run status, subscription status) are discriminated unions that make illegal states unrepresentable — a `success` run cannot exist without a `result`. `any` is never an acceptable resolution; `unknown` plus narrowing (or Zod validation) is the only escape hatch, at true external boundaries only. Every SSE/WebSocket event handler is exhaustive over its event union (`never`-checked default) so a new backend event type fails the build until handled. Generated OpenAPI types live in `lib/api/types/generated.ts`, regenerated not hand-edited (`typescript-expert`).

**Tailwind CSS v4.** CSS-first `@theme` configuration in `globals.css`; every color/spacing/radius/shadow/typography value comes from a token, arbitrary values (`w-[137px]`) are the exception. Class-based dark mode driven by stored user/workspace preference (theme-correct on first paint, no flash), not just `prefers-color-scheme`. Token naming follows `design-system-architect`'s `--color-{layer}-{purpose}-{state?}` scheme (`tailwind-css-expert`).

**shadcn/ui.** `components/ui/` holds only themed primitives; product components live in `components/<domain>/` composed from those primitives. Every component with more than one visual state exposes variants via `cva` with a typed props interface. A customized primitive never loses its built-in focus-trap or ARIA behavior (`shadcn-ui-expert`).

**Forms & validation.** Built on shadcn's `Form` + `react-hook-form` + Zod resolver, with Zod schemas colocated with their inferred types so validation and typing never drift; no uncontrolled/manual form state beyond a single search input (`shadcn-ui-expert`, `typescript-expert`).

**Components & state management.** All data access goes through `lib/api/` — no component calls `fetch` directly. Server-originated data (agent configs, run history, billing, marketplace) is TanStack Query with an explicit `staleTime`; ephemeral UI/canvas state is Zustand scoped to a single builder session (disposed on navigation); React Context only for cross-cutting rarely-changing values (auth, theme, feature flags). Named exports only; a file over ~300 lines is a signal to extract; no prop drilling beyond two levels (`senior-frontend-engineer`).

**Accessibility.** WCAG 2.2 AA is a merge gate, not a follow-up. Semantic HTML before ARIA; every interactive element has an accessible name; keyboard parity with mouse (the canvas ships a purpose-built keyboard model, not arrow-key drag emulation); focus is trapped and restored for every modal/drawer; status is never color-only. See Section 15 (`accessibility-expert`, `senior-frontend-engineer`).

**SEO.** Metadata via `generateMetadata` (never hardcoded `<head>`), dynamic sitemap driven by live marketplace data, JSON-LD generated server-side from the same data model the page renders, filtered/paginated marketplace views canonicalized or `noindex`ed. Owned by `seo-expert`, implemented by `nextjs-expert`.

**Performance.** Per-surface budgets (canvas, streaming log panel, dashboards) are enforced; heavy canvas-only/chart-only libraries are lazy-loaded via `next/dynamic`; long lists (trace events, run history) are virtualized. Core Web Vitals are gated in CI (`senior-frontend-engineer`, `performance-engineer`, `optimization-expert`).

**Animations.** Motion communicates state change, never decoration. High-frequency surfaces (log viewer, canvas during drag) animate only `transform`/`opacity` (GPU-friendly, no layout thrash); canvas drag is driven by motion values, not per-frame React state. Every non-essential animation honors `prefers-reduced-motion` with a verified fallback; durations/easings come from shared motion tokens (`framer-motion-expert`).

**Error/loading/empty states.** Every async surface implements loading, error, and empty states with the same rigor as the populated state. Empty states teach and prompt the next action; error states name the failing component and offer a specific remediation, never "Something went wrong" (`ux-designer`, `shadcn-ui-expert`). Loading (indeterminate spinner) is used only for sub-second waits; anything longer shows real incremental progress (`ux-designer`).

---

## 7. Backend Standards

Owned by `senior-backend-engineer` (architecture and code-review authority), with `fastapi-expert`, `python-expert`, `api-designer`, and `microservices-architect` as specialists.

**FastAPI.** Every route handler is `async def`; a dependency that must call sync code offloads via `run_in_threadpool` or a thread/process pool — never a blocking call inline (`fastapi-expert`, `python-expert`). Handlers are thin orchestration: resolve dependencies, delegate to a service-layer function, return a response model. No LLM/provider SDK call or agent-orchestration logic lives inside a route file. Auth and tenant resolution happen once in a shared dependency and are injected, never re-derived in a handler.

**Python.** Full type hints on every signature; `mypy` runs clean in CI. No synchronous blocking library (`requests`, sync DB driver, `time.sleep`) inside `async def`. CPU-bound work (tokenization, embedding batching) is explicitly offloaded. No bare `except:`; catch the narrowest actionable exception and re-raise with context (`raise ... from exc`). Structured logging via the shared logger — never `print()`. Config is a typed Pydantic `BaseSettings` loaded once, not scattered `os.environ` reads (`python-expert`).

**REST APIs.** Resources are nouns, actions are HTTP methods; plural collections; every resource scoped under its workspace in the URL (`/v1/workspaces/{workspace_id}/agents/{agent_id}/runs`). Cursor-based pagination for high-volume append-mostly collections (run history, trace events) with the standard `{"data", "next_cursor", "has_more"}` shape — never offset pagination on fast-appending data. Filtering exposed only on indexed fields. ISO 8601 UTC timestamps; opaque string IDs (ULID/UUID), never sequential integers. Owned by `api-designer`, implemented by `fastapi-expert`.

**Auth (authentication).** Identity is verified once at the gateway/dependency layer via a managed provider (Clerk or Better Auth) and passed down as a validated context; services trust a signed token, never re-implement token parsing. Session tokens are `httpOnly`/`Secure`/`SameSite` cookies, never `localStorage`. See Section 10 (`authentication-expert`).

**Authz & RBAC.** Every route touching a workspace-owned resource passes through the single shared permission-check dependency; no handler does its own role comparison. `workspace_id` is always resolved from the authenticated identity, never from client-supplied path/body/query. Workspace roles are a strict hierarchy: `owner > admin > member > viewer`, deny-by-default. API key scope is the intersection of the key's tier and the underlying identity's role. See Section 10 (`authorization-expert`).

**Validation.** Every request and response is a Pydantic v2 model with field-level constraints (`max_length`, `pattern`, enums) — no raw `dict`/`Any` I/O. Free-text fields that reach an LLM prompt have an enforced size cap to bound prompt-injection blast radius and cost (`fastapi-expert`, `secure-coding-expert`).

**Background jobs & queues.** All long-running agent execution runs in background workers on a Redis-backed queue (Redis Streams with consumer groups, or an Arq/Celery/RQ broker). `BackgroundTasks` is for sub-second, non-critical work only — never an agent run or a billing-affecting write. Run-triggering endpoints return `202 Accepted` with a `run_id` and status-poll URL (`fastapi-expert`, `system-designer`). Every worker task is idempotent so redelivery cannot double-execute or double-bill.

**Transactions.** Transactions are scoped as narrowly as possible; a DB transaction is never held open across an LLM call or external network call (it starves the connection pool). Billing usage aggregation and quota decrements use the isolation level `postgresql-expert` prescribes (`SERIALIZABLE` / `SELECT ... FOR UPDATE`) to prevent concurrent double-counting (`postgresql-expert`, `billing-expert`).

**Logging.** Structured JSON via the shared logger, always carrying `request_id`, `workspace_id`, and `run_id` where applicable, injected via request-scoped context (contextvars), not threaded manually. See Section 12 (`logging-expert`, `senior-backend-engineer`).

**Rate limiting.** Per-workspace and per-API-key limits (sliding window / token bucket in Redis) enforced at the gateway/middleware before any expensive work begins, keyed by `workspace_id`, failing closed under Redis unavailability (`redis-expert`, `saas-strategist`).

**API versioning.** Everything under `/v1`; a breaking change to an existing `/v1` contract requires a new version and a documented deprecation window, never an in-place change. Error `code` values are stable and additive once published (`api-designer`).

**Error responses.** One fixed envelope across every service: `{"error": {"code", "message", "details", "request_id"}}`, returned via a centralized exception handler — never a bare string or a leaked provider/internal exception message. Rate-limit/quota errors return `429` with `rate_limited`/`quota_exceeded` and `retry_after` where known (`api-designer`, `fastapi-expert`).

**Idempotency.** Run-triggering and billing-affecting endpoints require an `Idempotency-Key` header; replaying the same key returns the original response instead of re-triggering the action. The contract requirement is owned by `api-designer`; the Redis-backed implementation by `fastapi-expert`/`redis-expert`.

---

## 8. Database Standards

Owned by `database-architect` (relational schema authority), with `postgresql-expert` (query/runtime performance), `redis-expert` (in-memory layer), and `vector-database-expert` (semantic layer).

**PostgreSQL is the system of record.** Core entities: `users`, `workspaces`, `workspace_members` (with `role`), `agents`, `agent_versions`, `agent_runs`, `agent_run_steps`, `tool_calls`, `knowledge_bases`, `kb_documents`, `kb_chunks`, `billing_subscriptions`, `billing_usage_events`, `invoices`, `api_keys`, `audit_logs`. Every tenant-owned table has a non-null `workspace_id` with a foreign key to `workspaces(id)` and a leading index — a table without `workspace_id` is a bug unless it is explicitly global (`users`, platform `feature_flags`) (`database-architect`).

**Redis is never the system of record.** Everything in Redis must be reconstructable from Postgres (or safely lost). Redis is cache, session store, queue, distributed lock, and rate-limit counter only. Real-time usage counters in Redis are for UI display; final billing reads from durable `billing_usage_events`, reconciled nightly (`redis-expert`, `saas-strategist`, `billing-expert`).

**Vector database is the semantic layer, not the source.** `kb_chunks.embedding` and `marketplace_listings.embedding` hold vectors plus metadata; source content lives in Postgres/object storage. Every vector row carries `workspace_id`, and every similarity query is pre-filtered by `workspace_id` (never post-filtered on an unscoped top-k — that both leaks tenant data and degrades recall). Embeddings are versioned with `embedding_model` and `embedding_model_version`; a similarity search never mixes model versions (`vector-database-expert`).

**Migrations.** Alembic only; no manual DDL against any environment. Every migration is reversible with a working `downgrade()`. Adding a `NOT NULL` column to a large/hot table ships as two migrations (add nullable + backfill, then constraint) — never a single blocking migration. Indexes on live tables use `CREATE INDEX CONCURRENTLY`. Schema changes affecting a shared contract ship with a deprecation window, not a silent rename (`database-architect`, `postgresql-expert`).

**Indexing.** Composite indexes on tenant tables lead with `workspace_id` (e.g., `(workspace_id, created_at DESC)`); partial indexes for narrow hot subsets (e.g., `status IN ('queued','running')`). Every index is justified by an actual query pattern; every performance fix carries before/after `EXPLAIN (ANALYZE, BUFFERS)` at realistic scale, not against an empty dev DB (`postgresql-expert`).

**Relationships.** Foreign keys always declare an explicit `ON DELETE` behavior. Agent configuration (`agents.config`) is `jsonb` validated by an application-layer Pydantic schema — the DB stores flexibility, the API enforces shape (`database-architect`).

**Naming.** Tables plural snake_case; columns singular snake_case; foreign keys `<referenced_table_singular>_id`; timestamps `*_at` as `timestamptz` in UTC; booleans `is_*`/`has_*`. Redis keys `{env}:{service}:{domain}:{entity}:{id}[:{attribute}]`, tenant-namespaced where applicable, every key with an explicit TTL or a documented reason for persistence (`database-architect`, `redis-expert`).

**Performance.** All production traffic goes through PgBouncer (transaction pooling); no direct FastAPI-to-Postgres connections. High-volume tables are partitioned by `created_at` from their first migration; autovacuum is tuned for high-churn tables. Long-running analytical/reporting queries use a read replica or a dedicated low-priority pool, never the primary transactional pool (`postgresql-expert`).

**Auditing.** `audit_logs` is append-only — no UPDATE/DELETE grants for the application role. Soft delete (`deleted_at`) is the default for user-facing entities; hard deletes are reserved for GDPR/CCPA erasure via an explicit logged workflow (`database-architect`).

**Money.** All monetary values are integers in the smallest currency unit (cents), never floats, everywhere — schema, aggregation, proration, invoicing (`database-architect`, `billing-expert`). This is made explicit because it is asserted by two skills and touches real money.

**Backups.** Every stateful store (Postgres, Redis, vector DB) has a documented backup schedule, retention, and RPO/RTO, and a restore procedure that has actually been test-restored — an untested backup is a hypothesis, not a recovery plan (`cloud-architect`).

---

## 9. AI Standards

Owned by `ai-architect`, `prompt-engineer`, `rag-expert`, `mcp-expert`, `vector-database-expert`, `openai-expert`, and `openai-agents-sdk-expert`. This section is the concrete standards layer; Section 4 is the principles.

**Claude Code (build tool).** How the AgentVerse org uses Claude Code to build AgentVerse — planning mode before large changes, subagent delegation for genuinely independent work, self-review against the relevant skill's checklist before declaring done, and this skill library's maintenance — is owned by `claude-code-expert`. It is a build-process discipline, distinct from AgentVerse's own agent runtime.

**Provider abstraction.** Every LLM call goes through the provider-abstraction interface; no orchestration, route, or workflow code imports a provider SDK directly. The interface contract (methods, streaming event shape, error taxonomy) is owned with `ai-architect`; `openai-expert` implements OpenAI as one provider behind it, and adding another provider never touches orchestration or business logic. Provider-specific errors (rate limit, context-length, content-filter) are translated to AgentVerse's internal error taxonomy at the boundary (`ai-architect`, `openai-expert`).

**OpenAI integration.** Async client throughout; streaming by default for user-facing generation; native JSON-schema/structured-output mode (not prompt-only JSON) whenever the consumer is code; bounded exponential backoff with jitter on 429s; token usage recorded per call attributed to workspace/run; model choice resolved through the routing table, never hardcoded in feature code (`openai-expert`).

**Agents SDK runtime.** Where the runtime is built on the OpenAI Agents SDK, `Agent`/`Tool`/`handoff` configs are generated from stored agent configuration, tool wrappers validate arguments before executing and route through the tool-execution boundary, guardrails derive from declared scope and fail closed, session memory uses a durable backend matching the lifecycle, and SDK trace spans are translated into AgentVerse's own trace-event schema (the frontend never depends on SDK-internal trace formats). SDK version is pinned; upgrades are reviewed against the changelog (`openai-agents-sdk-expert`).

**MCP.** Consuming third-party MCP servers and (where exposed) AgentVerse's own MCP surface: transport chosen for the server's trust/location (stdio for tightly-controlled co-located, SSE/streamable HTTP for remote/third-party), tool schemas validated end-to-end, tool results sanitized before re-entering agent context (treated as untrusted external content, same as RAG chunks), and a failing/unreachable MCP server disables only its own tools for that run with a clear trace event — never crashes the run (`mcp-expert`).

**RAG.** Pipeline (rewrite → hybrid retrieve → rerank → assemble) owned by `rag-expert`; each stage justified by eval-set results. Citation metadata (`document_id`/`chunk_id`/location) flows through every stage into the final assembled context so answers trace to source. Context assembly respects the target model's real token budget (`rag-expert`).

**Embeddings.** Owned by `vector-database-expert`: HNSW indexes for latency-sensitive KB retrieval, cosine similarity consistently, embeddings tagged with model/version, similarity thresholds justified by a labeled eval set (not a guessed constant), and re-embedding after a model upgrade run as a resumable backfill + verified cutover (dual-write/shadow-read), never a blocking in-place rewrite.

**Chunking.** Content-aware, not one-size-fits-all: ~500-token prose chunks with ~50–100 token overlap tuned per document type, function/class-level for code, heading-bounded for markdown. Chunking functions are pure and unit-tested; ingestion is idempotent per `(kb_document_id, content_hash)` (`vector-database-expert`).

**Prompt templates.** Versioned artifacts in a prompt store (git history or a registry table), never inline literals; instructions, retrieved context, and user input are always structurally delimited so downstream content cannot be mistaken for instructions; user-authored builder templates get the same injection-resistant defaults. Output-format instructions specify the exact schema the consuming code expects (`prompt-engineer`).

**Memory.** Persistence backend matches the conversation/run lifecycle; multi-instance deployments never rely on in-process memory (`openai-agents-sdk-expert`, `redis-expert`).

**AI evaluation.** Golden datasets and scoring rubrics are structured data; deterministic checks first, LLM-as-judge only with a fixed reference-anchored rubric; cost and latency tracked per prompt variant; regression evals run on every prompt change and after any target-model change (`prompt-engineer`, `rag-expert`).

**Safety.** Untrusted content (tool output, fetched web content, uploaded documents, other users' shared content) reaching an LLM is potential prompt injection and is structurally isolated, never string-concatenated into instructions. See Section 10 (`security-engineer`, `owasp-expert`).

**Fallback strategy.** Every routing rule has a documented fallback model/provider; a prompt is unfinished until validated against its fallback as well as its primary (`ai-architect`, `openai-expert`, `prompt-engineer`).

---

## 10. Security Standards

Owned by `security-engineer` (architecture and threat modeling, final security authority), with `authentication-expert`, `authorization-expert`, `owasp-expert` (audit), `secure-coding-expert` (day-to-day coding rules), and `security-reviewer` (per-PR/release gate).

**OWASP.** AgentVerse is reviewed against the OWASP Top 10 mapped to its actual surfaces, not generic checklist boilerplate: A01 cross-workspace broken access control, A03 injection (SQL and prompt injection via tool/document content), A08 insecure deserialization of agent configs/imported definitions, A10 SSRF from agent-initiated outbound calls. Every applicable category gets an explicit "reviewed, no finding" or a filed finding with severity, reproduction steps, and a routed owner (`owasp-expert`).

**Zero trust.** No service-to-service call is trusted because it originates inside the network — each carries a verifiable service identity and is authorized per-call. No security control is client-side only; every browser-enforced control is re-enforced server-side (`security-engineer`).

**Authentication (who).** Email/password (bcrypt/argon2, never custom crypto), OAuth/SSO, and magic links via a managed provider; short-lived JWTs (checking `exp`/`iss`/`aud`) with rotating refresh tokens; API keys are workspace-scoped at issuance, hashed at rest (fast hash — they are already high-entropy), shown in full exactly once, and revocable. Auth failures return uniform, information-minimal errors. Authentication answers "who," never "what can they do" (`authentication-expert`).

**Authorization (what).** Deny-by-default RBAC (`owner > admin > member > viewer`) enforced server-side via the single shared permission-check dependency; resource-level permissions (view/edit/run/delete/share) compose with role; API key scope is the intersection of key tier and role. `403` for same-workspace permission gaps, `404` for cross-workspace resources (so a workspace's existence isn't leaked). Every protected route's denial is tested cross-role and cross-workspace (`authorization-expert`).

**Encryption.** TLS in transit; secrets and sensitive data encrypted at rest per the secrets/crypto posture; PII identified and handled under consistent data-protection controls (`security-engineer`, `secure-coding-expert`).

**Secrets.** Exactly one legitimate home (secrets manager / runtime environment) and zero legitimate appearances anywhere else — source, logs, error messages, client bundles, image layers. A missing secret fails startup loudly; `os.environ.get("KEY", "changeme")` fallbacks are prohibited. `NEXT_PUBLIC_*` variables are audited on every addition (they ship in the client bundle) (`secure-coding-expert`, `security-engineer`, `docker-expert`, `ci-cd-expert`). This cross-cutting invariant is unified here from many skills.

**Audit logs.** Authentication events, permission grants and denials on sensitive actions, and destructive operations are written to the append-only `audit_logs` table from the enforcement point (so they can't be bypassed) — without logging the credential itself (`authorization-expert`, `authentication-expert`, `database-architect`).

**Rate limiting.** Per-workspace/per-API-key, enforced at the gateway before expensive work, failing closed. See Section 7 (`redis-expert`, `security-engineer`).

**Input/output validation.** Validate at every trust boundary once via a typed Pydantic v2 schema (API bodies, query params, file uploads, and tool-call payloads re-entering the system); encode on output (React default escaping; `dangerouslySetInnerHTML` is grep-able, sanitized, and justified per use). No raw string-built SQL, shell commands, or file paths from untrusted input — parameterization/allowlisting is mandatory. Uploaded knowledge-base documents are content-sniffed (not trusting client MIME), size-capped, and stored with a generated filename outside the web root (`secure-coding-expert`).

**AI-specific threat surface.** Every agent-initiated outbound call (tool call, MCP endpoint, webhook fetch) routes through an egress control point that denies by default to RFC1918, link-local `169.254.0.0/16` (including cloud metadata IPs), and loopback — direct outbound sockets from workers are prohibited. Agent tool/code execution is isolated (sandboxed process/container/namespace) with no default access to internal service credentials or the primary database. Untrusted content is structurally delimited in prompts, never blurred into instructions (`security-engineer`, `owasp-expert`, `mcp-expert`).

**Dependency security.** `pip-audit`/`uv pip audit` and `npm audit`/`osv-scanner` run in CI as required checks on every PR touching manifests and on a nightly cadence; findings are triaged, not routinely ignored (`secure-coding-expert`).

**Privacy.** Agent execution logs (prompts, tool I/O, completions) are treated as potentially containing customer PII by default — redacted in general logs, with full content only in a separate access-restricted, shorter-retention stream. PII in analytics events or third-party integrations is reviewed with `security-engineer` before shipping (`logging-expert`, `analytics-engineer`).

**Review authority.** `security-engineer` owns architecture and threat models and is the final security authority; `security-reviewer` is the per-PR/release gate; `owasp-expert` runs standing audits; systemic findings escalate from the reviewer to the auditor, architectural findings to the engineer.

---

## 11. Testing Standards

Strategy owned by `testing-architect`; test planning and gatekeeping by `qa-engineer`; backend test code by `pytest-expert`; E2E browser tests by `playwright-expert`.

**Test pyramid.** The pyramid shape follows AgentVerse's actual risk surface: broad fast unit coverage concentrated on billing, auth, tenant isolation, and orchestration logic; a focused integration layer for data-layer and streaming correctness; a lean E2E layer reserved for what only a real browser can verify (canvas drag/connect, cross-page flows, streaming UI over real network timing). A bug class is caught at the cheapest layer capable of catching it (`testing-architect`).

**Unit tests.** Service-layer logic with LLM providers and the vector DB replaced by shared fakes from `tests/fakes/`; pure functions (routing, proration, permission checks, chunking) tested in isolation. Every async test is truly async; no exact-string assertions against LLM output (`pytest-expert`, `python-expert`).

**Integration tests.** Real Postgres and Redis (test containers or a dedicated test DB) for anything transactional, concurrency-sensitive, or migration-dependent — an "integration test" that mocks the database anyway gives false confidence. Marked and separated from the fast unit run. Multi-tenant fixtures include at least two workspaces so cross-tenant isolation bugs are structurally likely to surface (`pytest-expert`).

**E2E (Playwright).** Builder canvas (real mouse-driven drag/connect), streaming log viewer (eventually-consistent assertions over SSE, never `waitForTimeout`), auth, and billing flows. Tests are independent and order-agnostic (each creates its own workspace/run fixture via API), use role/label/testid locators, and assert both visible UI outcome and underlying state. A flaky test is root-caused, never retried-until-green (`playwright-expert`).

**Regression.** `qa-engineer` owns the pre-release regression plan, stating explicitly which flows are manually re-verified and which are trusted to automation. Cross-tenant isolation and billing-correctness are mandatory line items in every regression plan regardless of release size (`qa-engineer`).

**Performance testing.** Latency budgets (p50/p95/p99 per endpoint class), Core Web Vitals, load tests for SSE/WebSocket fan-out and dashboard-at-scale, and CI performance gates are owned by `performance-engineer`. See Section 17.

**Non-deterministic AI output.** Tested for structure and behavior (valid schema, tool-call shape, response addresses input, cost/latency bounds), never exact text; output-quality judgment routes to `prompt-engineer`'s eval harness and `rag-expert`'s retrieval metrics — never conflated with the fast pass/fail suite (`testing-architect`, `qa-engineer`).

**Coverage goals.** Risk-weighted per codebase area, not a uniform global percentage — must-cover logic (billing, auth, tenant isolation, orchestration) is held to a high bar; trivial code is not chased to 100%. Coverage is a signal, not the goal (`testing-architect`).

**Release quality gates.** CI stages run cheapest-first (lint/type-check → unit → integration → E2E smoke → full E2E), fail-fast; every gate actually blocks when violated, with a documented, owned exception process — no silent downgrade from blocking to advisory. Tests are non-negotiable for logic changes; if something genuinely can't be tested (e.g., pure UI), that is stated explicitly rather than claimed to work (`testing-architect`, `agentverse-master-ai-engineering-team`).

---

## 12. DevOps Standards

Practice owned by `devops-engineer`, coordinating `ci-cd-expert` (pipeline), `docker-expert` (images), `deployment-engineer` (execution), `cloud-architect` (topology), `infrastructure-engineer` (IaC), and `linux-expert` (OS).

**Docker.** Every service has a multi-stage Dockerfile whose final image contains no build toolchain, runs as a non-root user, and pins its base image version. No secret ever lives in an image layer — runtime injection only. `docker-compose up` from a clean checkout brings up the full local stack (Postgres, Redis, vector DB, all services) with health-check-gated startup order. Image tags are immutable and traceable to a commit (`sha-<short-sha>`), never `latest` for staging/production (`docker-expert`).

**CI/CD (GitHub Actions).** Every PR runs lint, type-check, and the relevant test suite as required checks; there is no "merge and fix CI later" for `main`. The same built image is promoted staging → production, never rebuilt per environment. Third-party actions are pinned to a SHA/exact version. Secrets are scoped per GitHub Environment and never printed to logs. Production deploys require an explicit approval gate. Pipeline behavior lives entirely in version-controlled YAML (`ci-cd-expert`).

**GitHub layer.** Branch protection enforces required reviewers and status checks and blocks direct pushes to `main`; CODEOWNERS maps paths to the owning role(s) from this library; paths touching auth/billing/RBAC require `security-engineer`/`authorization-expert` as an additional reviewer; PR titles are conventional-commit-formatted (they become the squash-merge message) (`github-expert`).

**Env vars.** Twelve-factor: dev/staging/production run the same container images and the same config shape, differing only in variable values (scale, data, secrets) — never in code branches (`if env == "production"` scattered in code is prohibited). Every required variable is validated present at startup (fail fast) and documented per platform in `.env.example` (`devops-engineer`, `deployment-engineer`).

**Deployment.** Frontend to Vercel (atomic deploys, instant rollback); FastAPI services and workers via Coolify/Railway/Docker with readiness-gated rolling/blue-green rollout so in-flight requests and SSE/WebSocket connections drain rather than drop. No deploy reaches production without first being deployed and health-verified in staging using the identical artifact. Every PR gets an automatic preview environment that never touches production data and is torn down on close (`deployment-engineer`).

**Rollback strategy.** Every release has a defined rollback action before it ships — at minimum "redeploy the previous image tag" (never a fresh build under incident pressure), with migration-specific rollback notes when schema changed. Database migrations are additive-and-backward-compatible at deploy time; destructive changes (column drops/renames) ship as a separate later migration after the old code path is retired, so a rollback never breaks still-deployed code (`devops-engineer`, `database-architect`). Feature flags decouple "deployed" from "released."

**Cloud topology & infrastructure.** Topology (compute placement, managed data stores, storage lifecycle, CDN, multi-AZ, auto-scaling policy, DR) is designed by `cloud-architect`; `infrastructure-engineer` encodes it as reviewed IaC (no manual console changes as standing practice; Postgres/Redis/vector DB reachable only via private networking); `linux-expert` sets OS-level resource limits so a runaway agent execution can't OOM co-located workers. CDN caching is never applied to authenticated or streaming (SSE/WebSocket) routes.

**Monitoring & health checks.** Every service exposes `/health` (liveness, process alive) and `/ready` (readiness, hard dependencies reachable) with correct distinct semantics before it can receive traffic.

**Logging & observability.** Overall observability strategy (RED/USE metrics, dashboards, alerting, SLOs, agent-run funnel end-to-end) is owned by `observability-engineer`; structured logging schema, levels, aggregation, retention, and PII redaction by `logging-expert`; distributed tracing (OpenTelemetry, one trace per run, context propagation across every boundary) by `opentelemetry-expert`. Logs, metrics, and traces correlate via shared `request_id`/`workspace_id`/`run_id`. Every paging alert has an owner, a defined severity/routing, and a linked runbook; agent execution (orchestration → tool call → LLM call → response) is a first-class dashboard/alert surface. Observability is a launch requirement, not a follow-up ticket.

---

## 13. Documentation Standards

Internal engineering docs owned by `documentation-engineer`; user-facing product docs by `technical-writer`. Docs-as-code: documentation lives in the repo, changes in the same PR as the code, and is enforced in PR review.

**README.** Every service's `README.md` documents its owned datastore(s), public contract location, upstream/downstream dependencies, and on-call runbook link (`principal-software-architect`).

**Architecture docs.** The service map / architecture overview and cross-service flow diagrams (Mermaid, checked into the repo) are kept in sync with `system-designer` and `microservices-architect`; hand-drawn images that silently rot are avoided in favor of text-defined diagrams (`documentation-engineer`).

**API docs.** API reference is 100% generated from each FastAPI service's OpenAPI schema plus docstrings — never hand-edited; fix the source and regenerate. Generation is a CI step, per service, matching real service boundaries (`documentation-engineer`, `api-designer`).

**ADRs.** One ADR per architecture decision, `docs/adr/NNNN-title.md`, immutable once accepted (a changed decision gets a new ADR that supersedes the old one with a forward link — never a silent edit or deletion), recording context, decision, consequences, and alternatives considered and rejected. A PR changing a public contract, data model, or architecture boundary without a corresponding doc update is a blocking review comment, not a follow-up ticket (`documentation-engineer`, `principal-software-architect`).

**Changelog.** Conventional-commit history is the changelog input; `technical-writer` compiles user-facing release notes per shippable release, grouped by user impact (Added/Improved/Fixed/Deprecated), from `product-owner`'s ticket-acceptance log (`git-expert`, `technical-writer`).

**Developer guides.** The engineer onboarding guide (`git clone` to merged PR) is validated by an actual new engineer walking through it at least quarterly; friction becomes doc fixes, not tribal knowledge (`documentation-engineer`).

**User-facing guides.** How-to guides (build an agent, connect an MCP tool, set up a workflow, read a trace, configure RBAC) are organized by product pillar, written against the live product (every step reproduced, never written from a spec), using real object names and the canonical glossary — one consistent product voice. User docs never expose internal implementation detail; they link to `documentation-engineer`'s reference for that (`technical-writer`).

**Code comments.** Comments explain the why where it isn't obvious from the code; docstrings state intent and non-obvious behavior, not a restatement of the signature. Comments are not a substitute for readable code (`agentverse-master-ai-engineering-team`, `python-expert`).

---

## 14. Git Standards

Git workflow owned by `git-expert`; the GitHub platform layer on top by `github-expert`.

**Branch naming.** Trunk-based development: short-lived feature branches off `main`, named `<type>/<ticket-id>-<kebab-desc>` (e.g., `feat/AV-142-03-mcp-parallel-tools`). `main` is always deployable. A branch open more than a few days is a signal to break the work down (`git-expert`).

**Commit format.** Conventional commits: `<type>(<scope>): <description>`, types limited to `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `build`, `ci`; scope is the service/pillar. Subject ≤72 chars, imperative mood; body explains why. Breaking changes marked with `!` and a `BREAKING CHANGE:` footer. Database migration commits stand alone, never squashed with unrelated application code (`git-expert`).

**PRs.** Every PR uses the template (linked ticket, summary, testing performed, screenshots for UI changes, rollback plan for infra/schema changes). Feature branches rebase onto `main` (not merge `main` in) to keep history linear; WIP/fixup commits are squashed before merge (`github-expert`, `git-expert`).

**Code reviews.** Every non-trivial PR gets a deliberate, standards-based review from `code-reviewer` before merge; CODEOWNERS routes it to the owning role. Reviews block merge only for correctness bugs, standards violations, missing tests on logic changes, or security/architecture concerns — style nits are marked non-blocking. Architecturally significant diffs route to `architecture-reviewer`; security-sensitive diffs to `security-reviewer` (`code-reviewer`).

**Merge rules.** Squash-merge to `main` only — linear history, no merge bubbles, so `git bisect`/`git blame` stay useful. No merge on a red required check, ever, including "just this once." Stale approvals are dismissed automatically when new commits land (`git-expert`, `github-expert`).

**Release strategy.** Semantic-versioned tags per service (`<service>-v<major>.<minor>.<patch>`) handed off to `ci-cd-expert`'s pipeline. Cross-service contract changes are versioned; the data-owning service's change lands before dependents (`git-expert`).

**Repository organization.** Independently deployable services default to their own repo; a monorepo is used only where services share a release cadence and deploy unit — a decision recorded and revisited as boundaries evolve, consulting `principal-software-architect` (`git-expert`).

---

## 15. UI/UX Standards

Design system architecture owned by `design-system-architect`; visual craft by `senior-ui-designer`; flows and usability by `ux-designer`; the non-negotiable accessibility gate by `accessibility-expert`. Copy by `copywriting-expert`.

**Design language.** The register of Apple, Linear, Stripe, Vercel, and Notion — restrained, confident, information-dense without clutter. Restraint over flourish: no gradient, shadow, or animation ships without a functional reason (state change, causality, focus). Consistency beats novelty; reuse an existing pattern before inventing one (`senior-ui-designer`).

**Design tokens (single source of truth).** All color, spacing, radius, shadow, typography, elevation, and motion values are Tailwind v4 `@theme` tokens layered primitive → semantic → component; no raw hex or arbitrary spacing in component markup. A new visual need resolves to an existing token, then an existing component variant, then (last resort, with sign-off) bespoke CSS. This is unified from `design-system-architect`, `tailwind-css-expert`, `senior-ui-designer`, and `shadcn-ui-expert`, which all assert it — `design-system-architect` owns the token system.

**Typography.** A modular scale (`xs`–`3xl`); base 14px for dense data surfaces (canvas, logs, tables), base 16px for form/settings/prose; one font family across the product; in-app headings max out at 32px (`design-system-architect`, `senior-ui-designer`).

**Color system.** Each hue as a 50–950 ramp; semantic tokens map steps per theme; status colors (running, success, warning, danger, info) each get a consistent fg/bg/border triad reused everywhere that status appears — a "success green" is never redefined per screen. Status is never conveyed by color alone; always paired with icon and/or text label (`design-system-architect`, `accessibility-expert`).

**Spacing.** 4px base unit (4, 8, 12, 16, 24, 32, 48, 64, 96); no values off the scale in product surfaces (`design-system-architect`).

**Icons.** One icon set only (lucide, matching shadcn/ui defaults) at consistent stroke width (`senior-ui-designer`).

**Accessibility (WCAG 2.2 AA floor, merge gate).** Keyboard parity with mouse (the canvas has a purpose-built keyboard interaction model — select-then-act, not arrow-key drag emulation); screen readers get scoped ARIA live regions for streaming logs that announce meaningful state transitions without over-announcing every token; focus moves into and is trapped within every modal/drawer and returns to the trigger on close; contrast ≥ 4.5:1 body / 3:1 large and UI; visible focus rings never suppressed without a compliant replacement; 44×44px minimum hit area; `prefers-reduced-motion` honored. axe-core runs in CI; manual keyboard + screen-reader passes catch what scanners can't. `accessibility-expert` is the last, non-negotiable gate before any UI surface ships.

**Responsive design.** Dashboards, settings, and marketplace are responsive down to standard mobile breakpoints; the builder canvas and log viewer are desktop/tablet-first with a documented minimum viewport below which they degrade to a simplified read-only view, never a broken layout (`tailwind-css-expert`, `design-system-architect`).

**Motion.** Purposeful, GPU-friendly on high-frequency surfaces, honoring reduced motion. Intent is specified by `senior-ui-designer`; durations/easings are shared tokens owned by `framer-motion-expert`. See Section 6.

**Consistency & states.** Every interactive component defines all states (default/hover/active/focus/disabled/loading/error/empty) with equal rigor — a screen designed only for the happy-path-with-data is unfinished. Dark and light theme are co-equal, each deliberately composed (dark-mode elevation via border + surface lightness, not shadow alone). Microcopy is direct, technically precise, no forced enthusiasm — matching the product's register, with pricing/entitlement copy mirroring `saas-strategist`'s matrix exactly and every CTA carrying exactly one action (`senior-ui-designer`, `ux-designer`, `copywriting-expert`).

**Flows.** System state is always legible during async/streaming operations; every empty and error state ends in one clear next action; onboarding reaches a real working agent in the fewest steps (prefer a modifiable template over a blank canvas); confirmation friction scales with reversibility (`ux-designer`). Complex async flows (the canonical run lifecycle `idle → queued → running → success/error/cancelled` plus streaming sub-state) are handed to engineering as explicit finite-state diagrams, matching `typescript-expert`'s `AgentRunState` union.

---

## 16. Code Quality Standards

Applies across the codebase; enforced by `code-reviewer` and each language/framework skill.

**Naming.** Consistent per ecosystem: Python snake_case, TypeScript PascalCase components / camelCase utilities and hooks, kebab-case services and files where conventional. Discriminant fields named consistently (`status` for lifecycle, `type` for event unions). No abbreviations in event/table/column names. Enums and role names defined once and imported, never duplicated string literals (`python-expert`, `typescript-expert`, `authorization-expert`, `analytics-engineer`).

**Folder organization.** Backend by clean-architecture layer within each service; frontend colocated by feature under its route segment; `components/ui/` for primitives and `components/<domain>/` for product components; tests mirror source structure. No cross-feature deep imports; a service's internal modules aren't imported by other services (`principal-software-architect`, `senior-frontend-engineer`, `python-expert`).

**Function size & complexity.** Handlers are thin; a frontend component file over ~300 lines signals extraction; no prop drilling beyond two levels; algorithmic complexity fixes state before/after complexity in a comment (`senior-frontend-engineer`, `optimization-expert`). Functions do one thing; deeply nested conditionals and god-objects are refactored, not extended.

**Refactoring.** Before adding logic, locate whether it already exists and consolidate rather than duplicate; when two skills' responsibilities blur, narrow scope and cross-reference rather than duplicate (`python-expert`, `claude-code-expert`). Refactors that consolidate duplication point reviewers to the new shared location.

**Technical debt.** Tracked explicitly, not silently accrued; `# @ts-ignore`/`# type: ignore` and any lint-rule suppression require an inline reason and a linked follow-up. A "temporary" shortcut (skipping a service boundary, accepting a raw `dict` body) is a real decision requiring the same scrutiny as a permanent one (`typescript-expert`, `architecture-reviewer`).

**Duplication rules.** DRY at the logic level (shared internal packages), the design level (single-source tokens), the contract level (generated types, one API error-code list), and the data level (one event/metric definition). Duplication is a defect to fix, not a convenience — but DRY never justifies coupling two services through a shared database. This reconciles `python-expert`, `design-system-architect`, `analytics-engineer`, and `microservices-architect`; where DRY and service-boundary isolation appear to conflict, isolation wins (a Master-consistent resolution, since a distributed monolith violates the Master's "one coherent, independently deployable" posture).

**No speculative complexity.** Build only what the current task needs — no unused abstractions, no hypothetical future-proofing, no half-finished scaffolding. The simplest fix that closes the gap wins (`agentverse-master-ai-engineering-team`, `optimization-expert`). Dead code, unused imports, and commented-out blocks are removed on sight (`python-expert`).

---

## 17. Performance Standards

Measurement, budgets, and diagnosis owned by `performance-engineer`; the fix implemented by `optimization-expert` (and `postgresql-expert`/`redis-expert` for their layers). The rule: measure, attribute, then fix — never optimize on intuition.

**Frontend performance.** Core Web Vitals (LCP, INP, CLS) tracked per surface (canvas, dashboard, run detail), gated in CI via Lighthouse CI and route-level JS bundle-size budgets that block merge on regression. The builder canvas (hundreds of nodes) and streaming trace view get particular attention (`performance-engineer`).

**Backend performance.** p50/p95/p99 latency budgets per endpoint class (CRUD, run-submission, dashboard aggregation, SSE/WebSocket connect), published before an endpoint ships. p95/p99 are tracked, not just averages — tail latency is what large enterprise workspaces feel. Every slow-path investigation decomposes end-to-end latency into network / API / DB / Redis / orchestration / LLM-call and names the dominant contributor; LLM-call latency is always reported separately, since it usually dominates and optimizing DB code when the LLM call is 80% of the time wastes effort (`performance-engineer`).

**Database performance.** Owned by `postgresql-expert`: index design, `EXPLAIN ANALYZE` at realistic scale, correct isolation levels, PgBouncer pooling, partitioning of high-volume tables, autovacuum tuning. No transaction held open across an LLM/external call. See Section 8.

**Caching.** Redis caching is an optimization with an explicit invalidation path, never a source of truth; correctness must hold with an empty cache. Correctness-sensitive caches (agent config) invalidate on the actual write path, not TTL alone. Every cache key has a TTL and a documented graceful-degradation behavior if Redis is briefly unavailable (`redis-expert`).

**Lazy loading.** Heavy canvas-only/chart-only libraries load via `next/dynamic` (with a matching loading fallback, no blank flash); route/feature code-splitting follows route boundaries so the dashboard never pays for canvas weight (`optimization-expert`, `nextjs-expert`).

**Bundle optimization.** Bundle-size budgets are CI gates; a code-split that shrinks the initial bundle but introduces a janky spinner on every canvas open is not a net win — perceived interactivity is protected (`optimization-expert`).

**Query optimization.** Every per-request list/filter query uses an index and filters on `workspace_id`; sequential scans are acceptable only for small/bounded/rare analytical queries. Bulk writes use multi-row `INSERT`/`ON CONFLICT`, not row-by-row loops (`postgresql-expert`).

**Closed loop.** No performance fix ships without a documented before/after measurement using the same method as the diagnosis; validation is done at realistic data volume and concurrency, correctness is preserved, and the CI regression gate is updated so the class of regression can't silently return. `performance-engineer` diagnoses; `optimization-expert` implements and reports the closed loop back.

---

## 18. Collaboration Model

AgentVerse is one organization of 80 skills. Every responsibility has exactly one primary owner. Where the library gives adjacent skills related work, this section names the single owner and the delegation chain, resolving any overlap per the skills' own Collaboration Rules.

### 18.1 Ownership map (single owner per responsibility)

**Product & requirements.** Vision/roadmap/PRDs/pricing initiation and the canonical activation metric: `product-manager`. Requirements decomposition, user-journey mapping, and edge-case cataloging: `business-analyst`. Backlog, ticket format, DoR/DoD, sprint mechanics, and acceptance validation: `product-owner`. Ceremony facilitation and impediment removal: `scrum-master`. Long-horizon process maturity and retro follow-through: `agile-coach`. (Resolution: `product-owner` owns backlog mechanics; `scrum-master` runs ceremonies on top of them and never reprioritizes tickets; `agile-coach` coaches both without redefining either.)

**Architecture.** System-wide structure, service boundaries, layering, cross-cutting standards, ADR process: `principal-software-architect` (final architecture authority). Feature-level end-to-end solution design: `solution-architect`. Distributed-systems mechanics (queues, workers, caching, HA, backpressure): `system-designer`. Service decomposition and inter-service communication: `microservices-architect`. Pre-implementation sign-off gate: `architecture-reviewer` (enforces, does not author).

**Backend.** Discipline lead and final backend sign-off: `senior-backend-engineer`. FastAPI mechanics: `fastapi-expert`. General Python quality/async/packaging: `python-expert`. REST contract shape/versioning/pagination/errors: `api-designer`. (Resolution: `api-designer` owns contract shape, `fastapi-expert` implements it, `senior-backend-engineer` ratifies; conflicts between them escalate to `senior-backend-engineer`.)

**Frontend.** Discipline lead and final frontend sign-off: `senior-frontend-engineer`. App Router/rendering/caching: `nextjs-expert`. Component/hook composition and render performance: `react-expert`. Type safety: `typescript-expert`. Styling tokens/theme: `tailwind-css-expert`. Component library: `shadcn-ui-expert`. Motion: `framer-motion-expert`.

**Data.** Relational schema and multi-tenancy modeling: `database-architect`. Query/runtime performance, indexing, partitioning, pooling: `postgresql-expert`. Cache/queue/lock/rate-limit layer: `redis-expert`. Semantic storage (embeddings, indexing, chunking): `vector-database-expert`. (Resolution: `database-architect` owns schema shape including the relational tenancy columns on vector metadata; `postgresql-expert` proposes indexing within that schema through it; `vector-database-expert` owns storage mechanics but inherits the `workspace_id` tenancy rule.)

**AI.** AI-specific orchestration architecture (topology, routing, handoff, reasoning loops): `ai-architect`. Customer-facing DAG workflow product feature: `ai-workflow-engineer`. Internal ops dogfooding automation: `ai-automation-engineer`. Prompt content, versioning, evals: `prompt-engineer`. Retrieval pipeline: `rag-expert`. MCP integration: `mcp-expert`. OpenAI provider integration: `openai-expert`. Agents-SDK runtime implementation: `openai-agents-sdk-expert`. (Resolution: `ai-architect` owns orchestration primitives; `ai-workflow-engineer` builds the product feature on top and never reimplements handoff/routing; `openai-agents-sdk-expert` implements the topology in SDK primitives without originating designs.)

**Security.** Architecture, threat models, final security authority: `security-engineer`. Identity verification: `authentication-expert`. Access control/RBAC: `authorization-expert`. Standing OWASP audit: `owasp-expert`. Day-to-day secure-coding rules: `secure-coding-expert`. Per-PR/release security gate: `security-reviewer`.

**DevOps.** Overall practice, environment strategy, release process, rollback design: `devops-engineer`. Pipeline mechanics: `ci-cd-expert`. Containerization: `docker-expert`. Deploy execution: `deployment-engineer`. Cloud topology design: `cloud-architect`. IaC implementation: `infrastructure-engineer`. OS-level concerns: `linux-expert`. GitHub platform: `github-expert`. Git workflow: `git-expert`.

**Observability.** Overall strategy/metrics/dashboards/alerts/SLOs: `observability-engineer`. Logging pillar: `logging-expert`. Tracing pillar: `opentelemetry-expert`. (Three separate pillars, correlated by shared IDs, never merged.)

**Testing.** Strategy/pyramid/gates/AI-output strategy: `testing-architect`. Test planning and quality gatekeeping: `qa-engineer`. Backend test code: `pytest-expert`. E2E browser tests: `playwright-expert`.

**Performance.** Measurement/budgets/diagnosis: `performance-engineer`. Fix implementation: `optimization-expert`.

**Documentation.** Internal engineering docs/ADRs/API reference/onboarding: `documentation-engineer`. User-facing product docs/release notes/glossary: `technical-writer`.

**Design.** Token/component-API system: `design-system-architect`. Visual craft: `senior-ui-designer`. Flows/usability/IA: `ux-designer`. Accessibility gate: `accessibility-expert`. Copy: `copywriting-expert`.

**Business & finance.** Strategic bets/PMF/GTM motion/fundraising: `startup-advisor`. Subscription lifecycle/metering/SaaS-metrics mechanics: `saas-strategist`. Concrete tier price points and packaging: `saas-pricing-expert`. Billing system internals (state machine, invoicing, proration): `billing-expert`. Stripe plumbing (Checkout, Billing Portal, webhooks): `stripe-integration-expert`. (Resolution of the pricing chain: `product-manager` initiates a pricing change; `saas-pricing-expert` sets the numbers and packaging; `saas-strategist` owns the surrounding lifecycle/metering/entitlement mechanics; `billing-expert` implements the internal logic; `stripe-integration-expert` handles everything that talks to Stripe. Each facet has exactly one owner.)

**Analytics.** Event taxonomy and ingestion pipeline: `analytics-engineer`. Dashboards, KPIs, cohort/exec reporting: `business-intelligence-expert`. (Resolution: `analytics-engineer` owns what is tracked and how it flows; `business-intelligence-expert` consumes modeled tables and never queries raw events; KPI definitions like "activation" trace to `product-manager`'s canonical definition.)

**Marketing.** GTM strategy/positioning/campaign orchestration: `marketing-strategist`. Technical/content SEO: `seo-expert`. Lifecycle/marketing email: `email-marketing-expert`. WhatsApp opt-in channel: `whatsapp-marketing-expert`. Copy: `copywriting-expert`. AARRR funnel instrumentation and experimentation: `growth-engineer`.

**Build tooling.** How the org uses Claude Code to build AgentVerse: `claude-code-expert`.

### 18.2 Decision hierarchy

1. `agentverse-master-ai-engineering-team` — final authority on any cross-discipline conflict or coherence question.
2. Discipline leads — `principal-software-architect` (architecture), `senior-backend-engineer` (backend), `senior-frontend-engineer` (frontend), `security-engineer` (security), `devops-engineer` (DevOps practice), `testing-architect` (testing strategy), `observability-engineer` (observability), `product-manager` (product) — own final sign-off within their discipline and arbitrate between their specialists.
3. Specialist skills — own the depth of their domain and escalate cross-cutting conflicts to their discipline lead, then to the Master.

### 18.3 Escalation path

A specialist raises a conflict rather than diverging silently. Backend contract-vs-boundary conflicts → `senior-backend-engineer`. Frontend pattern conflicts → `senior-frontend-engineer`. Service-boundary blast-radius → `principal-software-architect` (with `microservices-architect` input). Architecture-rooted process bottlenecks → from `agile-coach`/`scrum-master` to `principal-software-architect`. Security-architecture questions → `security-engineer`. Anything unresolved across disciplines → the Master.

### 18.4 Approval flow

Requirements approved by `product-manager` (with `business-analyst` edge-case sign-off) → architecture approved by `architecture-reviewer` (for significant designs) → implementation by the owning specialists under their discipline lead → tests by `pytest-expert`/`playwright-expert` against `qa-engineer`'s plan → reviews (below) → release gate by `final-qa-reviewer`.

### 18.5 Review flow

- `code-reviewer` — every non-trivial PR before merge; routes architecturally significant diffs to `architecture-reviewer` and security-sensitive diffs to `security-reviewer`.
- `architecture-reviewer` — sign-off gate on ADRs/new services/scalability-sensitive designs, against standards owned by the architecture skills.
- `security-reviewer` — per-PR/release security gate; escalates systemic findings to `owasp-expert`, architectural findings to `security-engineer`.
- `final-qa-reviewer` — aggregates code/architecture/security/QA sign-offs plus release notes and rollback plan into a single recorded go/no-go; never re-reviews from scratch, routes gaps back to the owning gate.

### 18.6 Conflict resolution

Every conflict is resolved by citing the owning skill's standard, then escalating up the decision hierarchy if unresolved, with the Master as final arbiter. No skill invents a competing standard inside a review or a PR. When a rule here reflects a resolution of two skills disagreeing, this constitution states it (e.g., DRY-vs-service-isolation in Section 16; the pricing ownership chain in 18.1).

---

## 19. Definition of Done

A feature is complete only when every item below is satisfied and tied to its reviewing skill. Partial completion is not done; "probably fine" never ships (`final-qa-reviewer`, `agentverse-master-ai-engineering-team`).

1. **Requirements approved** — PRD with persona, system touchpoints, success metric, and non-goals exists; acceptance criteria are testable; `business-analyst` has signed off edge cases. Owners: `product-manager`, `business-analyst`.
2. **Architecture approved** — any significant design (new service, datastore, cross-service call, scalability-sensitive path) carries a recorded `architecture-reviewer` verdict against an ADR, or an explicit "not applicable." Owner: `architecture-reviewer`.
3. **Security reviewed** — `security-reviewer` sign-off exists with zero unresolved blocking findings; auth/authz/tenant-isolation/secrets/prompt-injection/SSRF surfaces verified per its Review Checklist. Owner: `security-reviewer` (escalating to `security-engineer`/`owasp-expert` as needed).
4. **Tests passing** — unit/integration coverage proportional to risk with LLM/vector DB faked (`pytest-expert`), E2E for browser-only behavior with signal-based waits (`playwright-expert`), `qa-engineer`'s regression plan executed, and `testing-architect`'s CI quality gates green. No exact-match assertions on LLM output.
5. **Documentation updated** — public contract/schema/architecture changes have a doc update in the same PR (`documentation-engineer`); user-facing changes have accurate release notes and updated guides (`technical-writer`).
6. **Performance validated** — the surface has a documented latency budget (or Core Web Vitals budget) and a measured actual within it; any fix has before/after numbers; a CI regression gate exists. Owner: `performance-engineer`.
7. **Accessibility verified** — WCAG 2.2 AA confirmed: keyboard-only operation, screen-reader announcement of live content, focus management, contrast in both themes, `prefers-reduced-motion`. Owner: `accessibility-expert` (the last non-negotiable UI gate).
8. **Monitoring added** — `/health` and `/ready` present for new services; RED/USE metrics on a checked-in dashboard; new paging alerts have severity, routing, and a runbook; agent-execution observability end-to-end intact; structured logs with correlation IDs. Owner: `observability-engineer`.
9. **Deployment ready** — reproducible, reversible artifact; a defined one-action rollback path before shipping; migrations additive/backward-compatible at deploy time; environment parity preserved; validated in staging before production. Owners: `devops-engineer`, `deployment-engineer`.
10. **Final review complete** — `final-qa-reviewer` has aggregated all upstream sign-offs, confirmed release notes and rollback plan exist, and recorded an explicit go / no-go / go-with-conditions call against the release for future incident review. Owner: `final-qa-reviewer`.

Cross-cutting DoD invariants that apply to every change touching their surface: every DB query and cache key is `workspace_id`-scoped; run-triggering/billing endpoints enforce idempotency; no blocking call inside `async def`; every request/response is a Pydantic v2 model; the migration has a tested `downgrade()`.

---

## 20. Non-Negotiable Rules

These are hard lines. Violating one blocks merge or release regardless of deadline. Each traces to the skill(s) that establish it. When any of these conflicts with expedience, the Master's principles decide, and they always decide in favor of the rule.

1. **Never hardcode secrets.** No secret in source, logs, error messages, client bundles, or image layers; a missing secret fails startup loudly (no insecure fallback default). Secrets live only in the secrets manager / runtime environment (`secure-coding-expert`, `security-engineer`, `docker-expert`, `ci-cd-expert`, `authentication-expert`).
2. **Never bypass reviews.** No merge on a red required check, no unreviewed diff, no self-approved architecturally or security-significant change. `final-qa-reviewer` records an explicit go/no-go for every release (`code-reviewer`, `architecture-reviewer`, `security-reviewer`, `final-qa-reviewer`, `github-expert`).
3. **Never duplicate business logic.** Shared logic lives in one internal package; one source of truth for pricing config, event definitions, prompt templates, API error codes, and design tokens (`python-expert`, `saas-pricing-expert`, `analytics-engineer`, `api-designer`, `design-system-architect`).
4. **Never ignore tests.** Tests are mandatory for logic changes; if something genuinely can't be tested, say so explicitly rather than claim it works. No exact-string assertions against non-deterministic LLM output (`agentverse-master-ai-engineering-team`, `testing-architect`, `pytest-expert`).
5. **Never violate architecture.** No service reads another service's database directly; no long-running/LLM/agent work inline in a request; no new service without an ADR, `/health`, and `/ready`; no direct vector-DB access outside the `agent-runtime` fleet; the frontend never calls internal services directly (`principal-software-architect`, `microservices-architect`, `architecture-reviewer`).
6. **Never violate security.** Deny-by-default access control enforced server-side; `workspace_id` always from the authenticated identity, never client input; every agent-initiated outbound call routes through the egress control point blocking RFC1918/link-local/metadata IPs; untrusted content is structurally isolated from instructions; zero-trust between internal services (`security-engineer`, `authorization-expert`, `owasp-expert`).
7. **Never ignore accessibility.** WCAG 2.2 AA is the floor and a merge gate; no mouse-only interaction, no color-only status, no suppressed focus ring, no untrapped modal (`accessibility-expert`).
8. **Never merge broken code.** `main` is always deployable; CI (lint/type-check/test) green is required, not advisory; no "merge and fix later" (`ci-cd-expert`, `git-expert`, `github-expert`).
9. **Never ship undocumented APIs.** Every public contract change is versioned, reflected accurately in the generated OpenAPI, and documented in the same PR; breaking a `/v1` contract requires a new version and deprecation window (`api-designer`, `documentation-engineer`, `senior-backend-engineer`).
10. **Never introduce unnecessary complexity.** Build only what the current task needs — no speculative abstractions, no premature microservices, no exotic fix where a standard one closes the gap (`agentverse-master-ai-engineering-team`, `principal-software-architect`, `optimization-expert`).
11. **Tenant isolation via `workspace_id` is absolute.** Every tenant-owned table, every query, every cache key, every vector search, and every event carries and filters by `workspace_id`; cross-workspace access is denied without leaking existence. A tenant-scoped table or query missing it is a bug, always (`database-architect`, `authorization-expert`, `postgresql-expert`, `redis-expert`, `vector-database-expert`, `security-engineer`).
12. **No blocking calls in async code.** No synchronous HTTP client, sync DB driver, `time.sleep`, or unbuffered CPU-bound work inside `async def`; offload explicitly (`python-expert`, `fastapi-expert`, `senior-backend-engineer`).
13. **Redis is never the system of record.** Everything in Redis is reconstructable from Postgres or safely losable; final billing reads from durable `billing_usage_events`, never a live Redis counter alone (`redis-expert`, `saas-strategist`, `billing-expert`).
14. **Long-running agent execution is always a background worker job**, never inline in a request; every worker task is idempotent so redelivery can't double-execute or double-bill; every queue has a dead-letter queue and bounded retry (`system-designer`, `senior-backend-engineer`, `redis-expert`).
15. **Money is always integer cents**, never floating-point, everywhere it appears (`database-architect`, `billing-expert`).
16. **Every LLM call goes through the provider-abstraction layer** — no provider SDK imported from a route, workflow, or orchestration component (`ai-architect`, `openai-expert`, `solution-architect`).
17. **Every reasoning loop and workflow is bounded** by explicit step, cost, and time ceilings; an unbounded loop is a design-time bug (`ai-architect`).
18. **Every agent run is one connected trace** with correct parent/child nesting; trace context is never dropped across an async boundary (`opentelemetry-expert`).
19. **Migrations are reversible and additive-first**; destructive schema changes ship separately, after the old code path is retired, so a rollback never breaks deployed code (`database-architect`, `devops-engineer`).
20. **Destructive or hard-to-reverse actions require explicit confirmation** before proceeding — schema changes, data deletion, force pushes, infra edits (`agentverse-master-ai-engineering-team`, `claude-code-expert`, `linux-expert`).

---

*This constitution is enforced by every skill in the AgentVerse library and adjudicated, in any conflict, by `agentverse-master-ai-engineering-team`. It is a living document: changes to it follow the same ADR and review discipline as any architectural change, and must keep every one of the 80 skills' standards intact.*
