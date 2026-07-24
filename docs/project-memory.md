# AgentVerse — Project Memory

*The permanent memory of AgentVerse: who we are, what we are building, and why.*

This document is the durable product/business context for AgentVerse. It is deliberately **not** an engineering standards document — every engineering, architecture, security, testing, and design *rule* lives in the [AgentVerse Engineering Constitution](../CLAUDE.md) (`CLAUDE.md`), which is the highest-authority source of truth. Where a standard is relevant here, this file **cites** the constitution by section (e.g., "per `CLAUDE.md` §5") rather than restating it. The *reasoning* behind each technology choice lives in [`decision-log.md`](./decision-log.md); the *way we work* lives in [`ai-playbook.md`](./ai-playbook.md).

Read order for any task is fixed — see `ai-playbook.md` → Context Loading Strategy. `CLAUDE.md` always wins on any conflict; the Master skill `agentverse-master-ai-engineering-team` is the final arbiter (`CLAUDE.md` preamble, §18).

---

## 1. Product Identity

**Product Name.** AgentVerse.

**Tagline.** *Build, run, and operate reliable AI agents — as approachable as Vercel, as observable as Stripe.*

**Mission.** Make building, running, and operating reliable multi-agent AI systems as approachable, observable, and trustworthy as deploying to Vercel or paying with Stripe. A developer should be able to design an agent on a canvas, connect it to real tools over MCP, run it, watch every step stream live, understand exactly what it cost and why it succeeded or failed, and ship it to production — without assembling that stack themselves (`CLAUDE.md` §1).

**Vision.** Become the category-defining platform for agent orchestration — distinguished not by wrapping a single model in a chat box, but by *depth of orchestration* (planner/executor/critic, supervisor-worker, DAG workflows with human-in-the-loop) and *depth of observability* (one connected trace per run across orchestration, tool calls, and LLM calls, with per-run cost). That combination — orchestration + agent memory + observability — is the moat (`CLAUDE.md` §1; `startup-advisor`, `ai-architect`).

**Core Philosophy.** One engineering organization, not a collection of contractors. Every discipline operates as a facet of a single coherent team whose output reads as one aligned recommendation. We move from idea to production through discipline (requirements → design → implementation → tests → review → deploy), build only what the current task needs, and treat tests, security, and reversibility as non-negotiable defaults (`CLAUDE.md` §1, §16; `agentverse-master-ai-engineering-team`).

**Business Goals.**
- Reach and prove product-market fit against agent-platform competitors (LangChain-based platforms, CrewAI, Vertex Agent Builder, AWS Bedrock Agents) on orchestration depth and observability, measured by the Sean Ellis 40%-"very disappointed" threshold on active workspace admins (`startup-advisor`).
- Drive a healthy self-serve PLG funnel (Free → Pro) while opening a sales-assisted path for Team/Enterprise, without one audience degrading another's experience (`CLAUDE.md` §1; `product-manager`, `saas-strategist`).
- Grow net revenue retention through seat and usage expansion, with billing correct to the cent and reconciled against durable events (`CLAUDE.md` §8, Rule 13, Rule 15; `saas-strategist`, `billing-expert`).
- Sustain trust: published pricing, in-product cost transparency, and reliability good enough to run agents in production.

---

## 2. Product Description

**What AgentVerse is.** An enterprise SaaS platform for building, deploying, and orchestrating AI agents and multi-agent systems. Users design agents on a visual builder canvas, connect them to real tools (native, MCP-sourced, and knowledge-base retrieval), run them as bounded, observable executions, and operate them in production with live traces, per-run cost, quotas, and RBAC.

**The problems it solves.**
- *Assembly tax.* Building a production agent stack today means stitching together an orchestration framework, a vector store, tracing, a queue, billing, auth, and a UI. AgentVerse ships that stack coherently.
- *Opacity.* Most agent tooling is a black box — you cannot see why a run failed or what it cost. AgentVerse makes every run one connected trace (`CLAUDE.md` §4 Tracing, Rule 18) with per-run cost attribution.
- *Unreliability.* Unbounded loops, silent handoffs, and non-idempotent runs make agents unsafe in production. AgentVerse bounds every loop by step/cost/time, makes runs idempotent, and degrades gracefully (`CLAUDE.md` §4 Reliability, Rule 14, Rule 17).
- *Injection & tenant-leak risk.* Agents that call tools and read documents are a live prompt-injection and SSRF surface. AgentVerse structurally isolates untrusted content and routes every agent-initiated outbound call through an egress control point (`CLAUDE.md` §10, Rule 6).

**Why it exists.** Because the agent category is real but the tooling is immature: powerful primitives, no coherent, observable, trustworthy platform around them. AgentVerse is that platform.

**Why customers choose it over alternatives.** Orchestration depth and first-class observability, not a single-model chat wrapper; production-grade reliability and correctness (bounded runs, idempotency, billing to the cent); enterprise concerns (SSO, audit logs, tenant isolation) architected in rather than bolted on (`CLAUDE.md` §2 Enterprise Quality); and a developer experience in the register of Linear/Stripe/Vercel (`CLAUDE.md` §15).

---

## 3. Target Audience

AgentVerse serves three tiers of buyer across six practical personas (`product-manager`, `business-analyst`, `startup-advisor`, `saas-strategist`). The product must satisfy all without letting one audience's needs degrade another's (`CLAUDE.md` §1).

**Individual Developers** *(Free/Pro — self-serve, DX- and price-sensitive).*
- *Goals:* stand up a working agent fast; experiment without commitment; understand cost.
- *Pain points:* framework assembly overhead; opaque failures; surprise bills.
- *Expected workflow:* sign up → modify a marketplace template → run → read the trace → iterate. Activation is a first successful run within 24h (`CLAUDE.md` §1).

**AI Engineers** *(Pro/Team — power users).*
- *Goals:* multi-agent topologies, tool/MCP integration, prompt iteration with evals, model routing.
- *Pain points:* no rigorous eval loop; no per-step trace; hard to reason about handoffs and cost.
- *Expected workflow:* design topology on canvas → wire tools/knowledge bases → run and inspect trace → tune prompts against golden datasets → promote.

**Startups** *(Pro/Team).*
- *Goals:* ship an agent-powered feature without hiring an infra team; predictable spend.
- *Pain points:* limited engineering bandwidth; need reliability and observability out of the box.
- *Expected workflow:* template → customize → deploy → monitor usage against quota.

**Agencies** *(Team).*
- *Goals:* build and operate agents for multiple clients with clean separation and collaboration.
- *Pain points:* multi-client isolation, seat management, handoff of work.
- *Expected workflow:* workspace-per-client, role-based collaboration, template reuse across clients.

**SaaS Companies** *(Team/Enterprise).*
- *Goals:* embed agent capabilities into their own product; usage-based cost control; RBAC.
- *Pain points:* tenant isolation, cost attribution, API stability.
- *Expected workflow:* API-first integration behind scoped API keys; usage metering; workspace RBAC.

**Enterprise Teams** *(Enterprise — SSO, audit logs, dedicated resources, compliance).*
- *Goals:* run agents in production under governance; SSO; audit trails; dedicated Vector DB namespace; SLAs.
- *Pain points:* security review, compliance, procurement, isolation guarantees.
- *Expected workflow:* SSO onboarding → governed workspaces → audited actions → dedicated resources. Enterprise concerns are architected in, not bolted on (`CLAUDE.md` §2, §10).

---

## 4. Product Pillars

The five canonical pillars named in `CLAUDE.md` §1 (Agent Builder, Orchestration, Observability, Marketplace, Platform), expanded here with the supporting capabilities that hang off them (Workflow Automation, Knowledge Bases, Integrations, Collaboration).

**Agent Builder.** The visual canvas where an agent is authored — nodes, connections, tool/prompt/knowledge-base/model configuration, and a test-run affordance. An agent is stored, versioned configuration translated to a runtime agent at execution time, never hand-authored outside the builder data model (`CLAUDE.md` §4 Agents). Progressive disclosure: simple defaults first, advanced config on demand (`ux-designer`; `CLAUDE.md` §2 Simplicity).

**AI Orchestration.** The control plane deciding what happens next for a run. Supported topologies are explicit and the simplest sufficient one is the default: single-agent-with-tools, supervisor-worker, planner/executor/critic, sequential handoff. Every handoff carries a typed, versioned payload; every reasoning loop is bounded by step/cost/time (`ai-architect`; `CLAUDE.md` §4, Rule 17).

**Workflow Automation.** The user-facing, DAG-based multi-step workflow product feature — conditional branching, human-in-the-loop approval steps as a first-class node type with durable pause/resume, and workflow versioning (`ai-workflow-engineer`; `CLAUDE.md` §4 Human Approval). Built *on top of* orchestration primitives, never reimplementing them.

**Observability.** First-class execution traces: one connected trace per run spanning API → orchestration → worker → tool call → LLM call, with per-run cost, live streaming logs, and end-to-end agent-run dashboards/alerts. If a step cannot be represented in the trace UI, the design is not finished (`ai-architect`, `opentelemetry-expert`, `observability-engineer`; `CLAUDE.md` §4, §12, Rule 18).

**Marketplace.** Public, SEO-optimized catalog of agent templates and tool integrations — the acquisition and referral growth loop (a shared/public template drives new signups). Hybrid semantic + keyword search over listings (`growth-engineer`, `vector-database-expert`, `seo-expert`; `CLAUDE.md` §6 SEO).

**Knowledge Bases.** Per-workspace document stores powering RAG: ingest → chunk → embed → retrieve → rerank → assemble, with citations traceable to source documents. Storage mechanics owned by `vector-database-expert`; retrieval-pipeline behavior by `rag-expert` (`CLAUDE.md` §9 RAG/Embeddings/Chunking).

**Integrations.** Tools an agent can call — native tools, MCP connections (workspace-scoped, credential-isolated), and knowledge-base retrieval — all routed through the central tool-execution boundary for logging, auth, and rate-limiting (`mcp-expert`; `CLAUDE.md` §4 Tool Calling/MCP).

**Collaboration.** Workspaces as the tenant/isolation root, with RBAC (`owner > admin > member > viewer`), seat management, sharing, and team settings (`authorization-expert`; `CLAUDE.md` §10 Authorization).

**Platform Services.** The cross-cutting substrate: billing/subscriptions/usage metering, workspaces/RBAC, API keys, auth/SSO, notifications, and the public `/api/v1` gateway (`saas-strategist`, `billing-expert`, `authentication-expert`; `CLAUDE.md` §5, §7, §10).

---

## 5. Product Features

Master feature inventory, categorized by horizon. Roadmap sequencing is in §12; this is the *what*, grounded in `product-manager`'s pillar model.

**Current MVP.**
- Visual agent builder canvas (single-agent-with-tools authoring, versioned agent config).
- Single-provider agent runtime (OpenAI via the provider-abstraction layer) with bounded runs.
- Background-worker run execution with `202 Accepted` + status poll and live SSE execution-trace streaming.
- Per-run trace with step/tool-call/LLM-call nesting and per-run cost.
- Knowledge bases with RAG retrieval and citations.
- Native + MCP tool integration through the central tool-execution boundary.
- Workspaces, RBAC (`owner/admin/member/viewer`), API keys with scopes.
- Marketplace of starter templates (browse, use, share).
- Billing on Free/Pro/Team/Enterprise tiers via Stripe, usage metering, in-product usage panel.
- Prompt templates with versioning and an eval harness (golden datasets, regression evals).

**Future Features.**
- Multi-agent topologies in the builder (supervisor-worker, planner/executor/critic, sequential handoff).
- DAG-based Workflow Automation with conditional branching and human-in-the-loop approval nodes.
- Multi-provider model routing with documented fallbacks.
- Agent memory v2 (durable per-workspace conversation/session memory).
- Hybrid marketplace search and third-party template publishing.
- Internal dogfooding automations (support triage, onboarding) built on AgentVerse itself (`ai-automation-engineer`).

**Enterprise Features.**
- SSO/SAML, SCIM provisioning.
- Audit logs (append-only) and governance surfaces.
- Dedicated Vector DB namespace and dedicated worker resources.
- Custom pricing with an internal floor, invoicing, and SLAs.
- Compliance posture (e.g., SOC 2), scoped with `principal-software-architect` before external commitment (`startup-advisor`).

**Long-term Vision.**
- Open marketplace for third-party agent/tool developers (a two-sided ecosystem).
- AgentVerse's own MCP server surface exposing platform capabilities to external MCP clients (`mcp-expert`).
- Multi-region deployment and advanced reliability/compliance guarantees.
- Real-time/streaming multi-agent modalities (validated against orchestration throughput before commitment; `startup-advisor`).

---

## 6. Tech Stack

The **actual choices** are stated here as fact. The *reasoning, alternatives, and trade-offs* for each are in [`decision-log.md`](./decision-log.md) — this section and that log must never drift. Standards governing *how* each is used are in `CLAUDE.md` (cited inline).

| Layer | Choice | Reasoning |
|---|---|---|
| **Frontend** | Next.js 15 (App Router) + React 19 + TypeScript (strict) | decision-log: Why Next.js, Why TypeScript |
| **Styling / UI** | Tailwind CSS v4 (CSS-first `@theme` tokens) + shadcn/ui + Framer Motion | decision-log: Why Tailwind CSS, Why shadcn/ui |
| **Backend** | FastAPI + async Python (services: auth/workspace, orchestration/control-plane, billing, agent-runtime workers, integration/tool-gateway, notification) | decision-log: Why FastAPI |
| **Database** | PostgreSQL (system of record; Alembic migrations; PgBouncer pooling) | decision-log: Why PostgreSQL |
| **Caching / Coordination** | Redis (cache, session store, Streams queue, distributed locks, rate-limit counters) | decision-log: Why Redis |
| **Vector Database** | Vector DB semantic layer (pgvector or managed) with HNSW indexes | decision-log: Why Vector Database |
| **Authentication** | Managed provider (Clerk or Better Auth); short-lived JWTs, httpOnly cookies, hashed API keys | decision-log: (see Why RBAC / auth boundary; `CLAUDE.md` §10) |
| **Payments** | Stripe (Checkout, Billing Portal, idempotent webhooks) | decision-log: Why Stripe |
| **AI** | Provider-abstraction layer; OpenAI as first provider; OpenAI Agents SDK runtime; MCP for tools | decision-log: Why OpenAI, Why OpenAI Agents SDK, Why MCP |
| **Infrastructure** | Docker (multi-stage, non-root); private networking to data stores; IaC | decision-log: Why Docker |
| **Deployment** | Vercel (frontend, atomic deploys); Coolify/Railway/Docker (FastAPI services + workers) | `CLAUDE.md` §12 |
| **Monitoring** | OpenTelemetry tracing (one trace per run); RED/USE metrics; structured JSON logs; correlated by `request_id`/`workspace_id`/`run_id` | decision-log: Why Observability; `CLAUDE.md` §12 |
| **Testing** | pytest (unit/integration, async, LLM/vector faked); Playwright (E2E); eval harness for AI output | `CLAUDE.md` §11 |
| **Developer Tools** | Claude Code (build tool); GitHub + GitHub Actions CI; conventional commits; ADRs; docs-as-code | decision-log: Why Claude Code; `CLAUDE.md` §12–14 |

Monorepo unit: `apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `infra/` (`CLAUDE.md` §5; see §7 below).

---

## 7. Folder Structure

The expected repository structure, grounded in `principal-software-architect`'s monorepo layout and clean-architecture layering (`CLAUDE.md` §5, §16 — cited, not re-derived here).

```
AgentVerse/
├── CLAUDE.md                # Engineering Constitution — highest authority (do not duplicate)
├── docs/
│   ├── project-memory.md    # This file — product/business memory
│   ├── decision-log.md      # Dated engineering decisions + trade-offs
│   ├── ai-playbook.md       # How Claude Code works inside AgentVerse
│   ├── adr/                 # NNNN-title.md architecture decision records (§5, §13)
│   ├── architecture/        # Mermaid service map + cross-service flows (§13)
│   ├── systems/             # queues.md, redis-keys.md, capacity-*.md (system-designer)
│   └── runbooks/            # Failure-scenario runbooks (§12)
├── apps/
│   ├── web/                 # Next.js 15 App Router frontend (§6)
│   │   ├── app/             #   Route segments, colocated by feature: (dashboard)/(marketplace)/(auth)
│   │   ├── components/      #   ui/ (themed primitives) + <domain>/ (product components)
│   │   └── lib/             #   api/ typed client (generated types), hooks/, business logic
│   ├── api/                 # FastAPI gateway + services (§7)
│   │   └── <service>/       #   Per service, clean-arch layers:
│   │       ├── domain/      #     entities, zero framework imports
│   │       ├── application/ #     use cases / services
│   │       ├── infrastructure/#   Postgres, Redis, vector DB, LLM clients
│   │       └── interface/   #     FastAPI routers, Pydantic schemas
│   └── worker/              # Background agent-runtime workers (§5, §7)
├── packages/
│   └── contracts/           # Shared OpenAPI/TS types, generated (never hand-written) (§5)
└── infra/                   # Dockerfiles, IaC, docker-compose for local stack (§12)
```

Each independently deployable service ships its own `Dockerfile`, `.env.example`, and `README.md` documenting owned datastore(s), public contract, and dependencies (`CLAUDE.md` §5, §13). Backend organizes by clean-architecture layer within each service; frontend colocates by feature under its route segment; tests mirror source structure; no cross-feature deep imports and no cross-service internal-module imports (`CLAUDE.md` §16).

---

## 8. Architecture Overview

A narrative overview only — the governing rules are `CLAUDE.md` §5 (cited, not repeated).

**Frontend.** Next.js 15 App Router, Server Components by default with minimal justified client boundaries. On the builder canvas only the canvas/node/edge layer is client-rendered; live logs stream in a client leaf inside a server-rendered shell. Server state via TanStack Query, ephemeral UI state via Zustand, never mixed (`CLAUDE.md` §6; `nextjs-expert`, `senior-frontend-engineer`).

**Backend.** FastAPI services split by bounded context — `auth`/`workspace`, `orchestration` (control plane), `agent-runtime` worker fleet, `billing`, `integration`/tool-gateway, `notification`. Handlers are thin; business logic lives in the service layer; no LLM/agent logic in a router (`CLAUDE.md` §5, §7; `microservices-architect`, `fastapi-expert`).

**AI.** Every LLM call goes through the provider-abstraction layer (`CLAUDE.md` Rule 16). The `agent-runtime` fleet executes run steps; the OpenAI Agents SDK realizes topologies designed by `ai-architect`; MCP tools and RAG retrieval route through the central tool-execution boundary. One connected trace per run (`CLAUDE.md` §4, §9).

**Database.** PostgreSQL is the system of record; Redis is cache/queue/coordination (never source of truth); the Vector DB is the semantic layer (never the source). Every tenant-owned row, query, cache key, and vector search is `workspace_id`-scoped (`CLAUDE.md` §8, Rule 11, Rule 13).

**Infrastructure.** Dockerized services; the frontend on Vercel; FastAPI services and workers via Coolify/Railway/Docker with readiness-gated rollout; data stores reachable only over private networking; every service exposes `/health` and `/ready` (`CLAUDE.md` §12).

**External Services.** OpenAI (LLM/embeddings via the abstraction), Stripe (billing), the managed auth provider (Clerk/Better Auth), and third-party MCP servers (`CLAUDE.md` §3 SOLID — vendor SDKs behind adapters).

**Communication.** Async by default (Redis Streams/pub-sub) for anything not needing an immediate answer; synchronous REST only for tight-latency request-time needs, each with a timeout and circuit-breaker; the frontend only ever talks to the public `/api/v1` gateway (`CLAUDE.md` §5; `microservices-architect`, `system-designer`).

**Deployment.** Same built image promoted staging → production; additive-first reversible migrations; a defined one-action rollback before every release; PR preview environments that never touch production data (`CLAUDE.md` §12).

---

## 9. Design Language

Standards owned by `CLAUDE.md` §15 (cited). This section describes the intended *look and feel*.

**Visual Style.** The register of Apple, Linear, Stripe, Vercel, and Notion — restrained, confident, information-dense without clutter. Hierarchy before decoration; one unambiguous focal point per screen; density with breathing room for technical surfaces (canvas, logs, tables) (`senior-ui-designer`).

**Brand Personality.** Professional infrastructure tooling, not a consumer toy. Serious, precise, quietly premium. Motion is fast and purposeful; the canvas feels like Figma/Miro, not a bouncy wizard.

**Color Philosophy.** Neutral surface/text scales plus a single brand accent and a fixed status palette (running, success, warning, danger, info), each with a consistent fg/bg/border triad reused everywhere — "success green" is never redefined per screen. Status is never conveyed by color alone (`CLAUDE.md` §15; `design-system-architect`, `accessibility-expert`).

**Typography.** One font family across the product; modular scale `xs`–`3xl`; base 14px for dense data surfaces, 16px for form/prose; in-app headings max out at 32px (`CLAUDE.md` §15).

**Spacing.** 4px base unit (4, 8, 12, 16, 24, 32, 48, 64, 96); no off-scale values in product surfaces (`CLAUDE.md` §15).

**Animation Style.** Motion communicates state change and causality, never decoration; GPU-friendly (`transform`/`opacity`) on high-frequency surfaces; durations/easings from shared motion tokens; `prefers-reduced-motion` always honored (`CLAUDE.md` §6, §15; `framer-motion-expert`).

**Accessibility.** WCAG 2.2 AA is the floor and a merge gate — keyboard parity, scoped ARIA live regions for streaming logs, focus trap/restore, contrast, 44×44px hit areas, reduced-motion (`CLAUDE.md` §15, Rule 7; `accessibility-expert`). Dark and light theme are co-equal, each deliberately composed.

---

## 10. Brand Voice

How AgentVerse communicates: professional, technical, clear, helpful, confident, never overhyped. Microcopy is direct and technically precise with no forced enthusiasm — the register of Linear/Vercel, not consumer-app cheerfulness (`ux-designer`, `copywriting-expert`; `CLAUDE.md` §15). Every factual claim in marketing copy is verifiable against the shipped product (`CLAUDE.md` §2 Transparency).

- **Empty state.** Good: "No agents yet. Start from a template to reach a working agent in a few steps." Not: "It's a little lonely here! 🎉 Create your first agent!"
- **Error state.** Good: "Tool call to `search_web` timed out after 30s. Increase the timeout or check the tool's API key." Not: "Something went wrong. Please try again."
- **Pricing.** Good: "$X/mo, includes N,000 agent runs. Additional runs: $Y per 1,000." Not: vague "contact us for pricing" on a self-serve tier.
- **Confirmation.** Friction scales with reversibility — a named confirmation for destructive/billing-affecting actions, zero friction for reversible ones (`ux-designer`).

Pricing/entitlement copy mirrors `saas-strategist`'s matrix exactly; every CTA carries exactly one action (`CLAUDE.md` §15).

---

## 11. Success Metrics

Canonical definitions established in `CLAUDE.md` §1 and owned by `product-manager` / `saas-strategist` / `growth-engineer` / `business-intelligence-expert`. Not reinvented here.

- **Activation.** A `run_completed` within 24h of workspace creation (a first successful agent run) — the canonical activation metric and the single highest-leverage number to move (`CLAUDE.md` §1; `product-manager`, `growth-engineer`).
- **Retention.** A workspace with ≥1 successful run in each of N consecutive weeks; reported as a cohort curve, not a blended number (`growth-engineer`).
- **Expansion.** Seat growth and usage growth (usage-quota-driven upgrade rate); measured via NRR (`saas-strategist`, `business-intelligence-expert`).
- **Reliability.** Run success rate; graceful degradation under load; billing correct to the cent reconciled against durable `billing_usage_events` (`CLAUDE.md` §2, Rule 13).
- **Performance.** p50/p95/p99 latency budgets per endpoint class (with LLM-call latency reported separately) and Core Web Vitals per surface, both CI-gated (`CLAUDE.md` §17; `performance-engineer`).
- **Revenue.** MRR/ARR, NRR, GRR, logo churn, revenue churn, LTV:CAC — computed per cohort with documented formulas (`saas-strategist`).
- **Customer Satisfaction.** PMF signal via the Sean Ellis survey to active workspace admins (40%-"very disappointed" threshold); churn diagnosed by cohort and reason code (`startup-advisor`, `saas-strategist`).

Vanity totals (raw signups) are never treated as success (`CLAUDE.md` §1; `startup-advisor`).

---

## 12. Long-Term Roadmap

Concrete, sequenced phases grounded in `product-manager`'s now/next/later roadmap thinking and `startup-advisor`'s staging. Dates are ranges; each phase gates the next on evidence, not calendar.

**Phase 1 — MVP foundation.** Single-provider agent runtime (OpenAI via the abstraction), visual agent builder for single-agent-with-tools, background-worker execution with live SSE traces and per-run cost, knowledge bases + RAG, native/MCP tools, workspaces + RBAC, Stripe billing on four tiers, prompt versioning + eval harness, marketplace of starter templates. Goal: strong activation rate.

**Phase 2 — Depth of orchestration.** Multi-agent topologies in the builder (supervisor-worker, planner/executor/critic, sequential handoff), typed/versioned handoff contracts, model-routing with documented fallbacks, agent memory v2. Goal: differentiate on orchestration depth.

**Phase 3 — Workflow Automation & collaboration.** DAG-based workflows with conditional branching and human-in-the-loop approval nodes, workflow versioning, richer team collaboration and sharing, hybrid marketplace search. Goal: Team-tier expansion and retention.

**Phase 4 — Growth loops & multi-provider breadth.** Template-sharing and referral growth loops instrumented and optimized, additional LLM providers behind the abstraction, third-party template publishing, dogfooded internal automations. Goal: acquisition efficiency and loop efficiency > 1.

**Phase 5 — Full marketplace + enterprise compliance.** Open two-sided marketplace for third-party agent/tool developers, AgentVerse's own MCP server surface, SSO/SCIM, audit logs, dedicated resources, SOC 2 and enterprise SLAs, multi-region. Goal: enterprise-led expansion and compliance-gated deals.

---

## 13. Known Constraints

- **Budget.** Lean team; prefer boring, proven technology over novel tools absent a concrete constraint; build only for today plus one known horizon (`CLAUDE.md` §3 KISS, §16, Rule 10).
- **Scalability.** Long-running agent execution must be background work, never inline; high-volume tables partitioned from first migration; worker fleets scale on queue depth; no single point of failure in the hot path (`CLAUDE.md` §5, §8, §17; `system-designer`).
- **Maintainability.** One coherent team, one owner per responsibility; the execution path traceable by directory names; ADRs for decisions of consequence; docs-as-code (`CLAUDE.md` §3, §13, §18).
- **Security.** Tenant isolation via `workspace_id` is absolute; deny-by-default RBAC; egress control on agent-initiated calls; untrusted content structurally isolated; secrets only in the secrets manager (`CLAUDE.md` §10, Rules 1, 6, 11).
- **Performance.** Per-surface latency and Core Web Vitals budgets, CI-gated; measure-attribute-fix, never optimize on intuition; LLM-call latency isolated in every diagnosis (`CLAUDE.md` §17).
- **AI Cost.** Model routing is a deliberate cost/quality/latency decision; every reasoning loop bounded by step *and* cost *and* time; every LLM call records token usage attributed to workspace/run; usage priced above marginal cost and shown in-product before the invoice (`CLAUDE.md` §4; `ai-architect`, `saas-pricing-expert`).
- **Compliance.** Enterprise compliance (SOC 2, on-prem/dedicated Vector DB) is real work scoped with `principal-software-architect` before it is promised externally; PII in agent logs treated as sensitive by default (`CLAUDE.md` §10 Privacy; `startup-advisor`).

---

## 14. Future Vision

- **1 year.** A proven MVP with strong activation, multi-agent orchestration depth shipped, model routing with fallbacks, and the beginnings of Workflow Automation — a credible PMF story against agent-platform competitors, grounded in real instrumented metrics (`startup-advisor`).
- **3 years.** The reference platform for building and *operating* production agents: mature workflows with human-in-the-loop, deep observability as a recognized differentiator, Team-tier expansion, and enterprise features (SSO, audit logs, dedicated resources) in market.
- **5 years.** The category-defining agent-orchestration platform with an open two-sided marketplace ecosystem, AgentVerse's own MCP surface, multi-region enterprise deployments, and compliance posture that makes it the default trustworthy choice for running multi-agent systems in production — moat intact on orchestration + agent memory + observability (`CLAUDE.md` §1; `startup-advisor`, `ai-architect`).

---

*This is living memory. It is updated through the process in [`ai-playbook.md`](./ai-playbook.md) → Continuous Improvement Process, and it never contradicts `CLAUDE.md`. On any conflict, `CLAUDE.md` and the Master skill decide.*
