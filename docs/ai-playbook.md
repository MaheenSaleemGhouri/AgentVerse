# AgentVerse — AI Playbook

*How Claude Code works inside AgentVerse.*

This playbook is the operating procedure for AI-assisted engineering on AgentVerse. It sequences the workflows, defines how the 80 skills collaborate, and provides the standing checklists. It is **subordinate to** the [Engineering Constitution](../CLAUDE.md) (`CLAUDE.md`) and complements [`project-memory.md`](./project-memory.md) (product context) and [`decision-log.md`](./decision-log.md) (technical precedent). Where the constitution defines a *standard*, this playbook **cites** it and adds only operational *sequencing* on top — it never restates a rule the constitution already owns.

The final authority on any conflict is `CLAUDE.md` and the Master skill `agentverse-master-ai-engineering-team` (`CLAUDE.md` preamble, §18).

---

## 1. Planning Workflow

Every non-trivial change moves through the Master skill's Idea → Production discipline: **requirements → design → plan → implementation → tests → review → deploy** (`agentverse-master-ai-engineering-team` Operating Principles 1; `CLAUDE.md` §1). Don't skip to code.

Concrete sequence:
1. **Classify the task** (`claude-code-expert`). Trivial/scoped (a bug fix, a copy change) → implement directly. Large/ambiguous/cross-cutting, or touching auth/billing/tenancy/migrations → state a plan first.
2. **Requirements.** Frame the problem: persona, system surface, and the metric it moves — if it can't name all three it isn't ready (`product-manager`; `CLAUDE.md` §2). Edge cases are first-class, not an appendix (`business-analyst`).
3. **Design.** Produce the solution/architecture design (§2 below). Any significant design gets an ADR before implementation (`CLAUDE.md` §5).
4. **Plan.** State affected areas, the skills/standards that apply, and the order of work; call out assumptions to confirm and identify genuinely parallelizable sub-tasks for subagent delegation (`claude-code-expert`).
5. **Implementation → Tests → Review → Deploy readiness** proceed per §3–§6. Acceptance criteria are Given/When/Then against real UI/API surfaces (`product-manager`, `qa-engineer`).

No speculative engineering: build only what the current task needs (`CLAUDE.md` §16, Rule 10).

---

## 2. Architecture Workflow

Architecture decisions are made by the architecture skills and gated before implementation starts (`CLAUDE.md` §5, §18).

- **System-wide** structure/boundaries/layering/ADR process → `principal-software-architect` (final architecture authority).
- **Feature-level** end-to-end solution design → `solution-architect`.
- **Distributed-systems mechanics** (queues, workers, caching, HA, backpressure) → `system-designer`.
- **Service decomposition & inter-service communication** → `microservices-architect`.

Flow: the proposing architect authors the design and ADR (`docs/adr/NNNN-title.md`, Context/Decision/Consequences/Alternatives) → escalate to `architecture-reviewer` for the sign-off **gate** (Approved / Approved-with-Conditions / Rejected-and-return; the reviewer enforces, never redesigns) → recorded verdict on the ADR for `final-qa-reviewer` to reference at release. Any new service, datastore, cross-service dependency, or scalability-sensitive feature requires this before code starts (`CLAUDE.md` §5, Rule 5). AI-specific architecture (topology, routing, handoff) is owned by `ai-architect`, escalating system-level fit to `principal-software-architect`.

---

## 3. Implementation Workflow

Coding is done by the owning specialist under their discipline lead (`CLAUDE.md` §18). Invoke the skill that owns the layer:

- **Backend route/streaming** → `fastapi-expert`; **general Python/async/service logic** → `python-expert`; **API contract shape** → `api-designer`; ratified by `senior-backend-engineer`.
- **Frontend rendering/routing** → `nextjs-expert`; **components/hooks/render perf** → `react-expert`; **types** → `typescript-expert`; **styling/tokens** → `tailwind-css-expert`; **components** → `shadcn-ui-expert`; **motion** → `framer-motion-expert`; under `senior-frontend-engineer`.
- **Data** → `database-architect`/`postgresql-expert`/`redis-expert`/`vector-database-expert`.
- **AI** → `ai-architect` (design), `openai-agents-sdk-expert`/`openai-expert` (runtime), `mcp-expert` (tools), `prompt-engineer` (prompts), `rag-expert` (retrieval).
- **Billing/auth** → `stripe-integration-expert`/`billing-expert`/`saas-strategist`, `authentication-expert`/`authorization-expert`.

Apply the engineering principles by citation, not restatement: Clean Architecture layering, SOLID adapters, DRY via shared packages, KISS, separation of concerns (`CLAUDE.md` §3). **TDD expectation:** tests are non-negotiable for logic changes and ship with the change; if something genuinely can't be tested (e.g., pure UI), say so explicitly rather than claim it works (`agentverse-master-ai-engineering-team` Operating Principle 3; `CLAUDE.md` §11, Rule 4). Before writing new logic, locate whether it already exists and consolidate (`CLAUDE.md` §16). Every non-trivial change gets a self-review pass against the owning skill's checklist before it is presented as done (`claude-code-expert`).

---

## 4. Review Workflow

Reviews run as a gate sequence; each gate enforces standards owned elsewhere and routes rather than re-litigates (`CLAUDE.md` §14, §18.5).

1. **`code-reviewer`** — every non-trivial PR before merge: correctness, readability, standards conformance (cited to the owning language/framework skill), test coverage proportional to risk. Blocks only for correctness bugs, standards violations, missing tests on logic changes, or security/architecture concerns; style nits marked non-blocking.
2. **`architecture-reviewer`** *(if architecturally significant)* — routed by `code-reviewer` when a diff introduces a new service, datastore, or cross-service call; verifies against §2's standards; records a verdict on the ADR.
3. **`security-reviewer`** *(if security-sensitive)* — routed when a diff touches auth, authz, tenant isolation, secrets, user input, streaming endpoints, or LLM prompt construction; a `blocked` verdict halts merge; systemic findings escalate to `owasp-expert`, architectural findings to `security-engineer`.
4. **`final-qa-reviewer`** — the release gate: aggregates the above sign-offs plus QA/testing results, release notes, and rollback plan into one recorded go / no-go / go-with-conditions. It confirms sign-offs exist; it never re-reviews from scratch and routes gaps back to the owning gate.

---

## 5. Testing Workflow

Testing follows the pyramid shaped to AgentVerse's real risk surface (`CLAUDE.md` §11).

1. **Strategy & gates** → `testing-architect`: pyramid ratio, risk-weighted coverage targets (billing, auth, tenant isolation, orchestration held highest), CI gate block/advisory status, and the AI-output testing strategy (structural pytest assertions vs. eval-harness quality judgment — never conflated, never exact-match on LLM output).
2. **Planning & gatekeeping** → `qa-engineer`: test-case matrices, bug triage/severity, and the pre-release regression plan (cross-tenant isolation and billing correctness are mandatory line items every release).
3. **Backend tests** → `pytest-expert`: async unit tests with LLM/vector DB faked, integration tests against real Postgres/Redis (multi-tenant fixtures with ≥2 workspaces), streaming and worker tests.
4. **E2E tests** → `playwright-expert`: canvas drag/connect, streaming log viewer (signal-based waits, never `waitForTimeout`), auth, billing — independent, order-agnostic, asserting both UI outcome and underlying state.
5. **CI ordering** cheapest-first: lint/type-check → unit → integration → E2E smoke → full E2E, fail-fast; every gate actually blocks when violated (`CLAUDE.md` §11). Flaky tests are root-caused, never retried-until-green.

---

## 6. Deployment Workflow

Releases are reproducible, reversible, and staged (`CLAUDE.md` §12).

- **Pipeline** → `ci-cd-expert`: GitHub Actions runs required checks per PR; the same built image is promoted staging → production, never rebuilt per environment; production deploys require an approval gate.
- **Practice & coordination** → `devops-engineer`: environment parity (twelve-factor), release process, and rollback design.
- **Execution** → `deployment-engineer`: Vercel for the frontend (atomic deploys, instant rollback); Coolify/Railway/Docker for FastAPI services and workers with readiness-gated rolling/blue-green rollout so in-flight requests and SSE/WebSocket connections drain. No production deploy without a health-verified staging deploy of the identical artifact; every PR gets a preview environment that never touches production data.
- **Rollback procedure.** Every release has a defined rollback action *before* it ships — at minimum "redeploy the previous image tag" (never a fresh build under incident pressure) — with migration-specific notes when schema changed. Migrations are additive/backward-compatible at deploy time; destructive changes ship as a separate later migration after the old code path is retired, so a rollback never breaks deployed code (`CLAUDE.md` §12, Rule 19). Feature flags decouple "deployed" from "released."

---

## 7. Documentation Workflow

Docs-as-code: documentation lives in the repo, changes in the **same PR** as the code, and is enforced in PR review (`CLAUDE.md` §13).

- **Internal engineering docs** (ADRs, architecture/service map, OpenAPI-generated API reference, onboarding) → `documentation-engineer`. API reference is 100% generated from each service's OpenAPI schema — never hand-edited; fix the source and regenerate.
- **User-facing docs** (build-an-agent, connect-an-MCP-tool, workflow setup, read-a-trace, RBAC guides, release notes) → `technical-writer`, organized by product pillar, written against the live product in one consistent voice (`project-memory.md` §10 Brand Voice).
- **Synchronization mechanism.** A PR changing a public contract, data model, or architecture boundary without a corresponding doc update is a **blocking** review comment, not a follow-up ticket (`CLAUDE.md` §13, Rule 9). ADRs are immutable once accepted — a changed decision gets a new ADR that supersedes with a forward link. The onboarding guide is validated by a real new engineer at least quarterly.

---

## 8. AI Collaboration Rules

AgentVerse is one organization of 80 skills with exactly one primary owner per responsibility. The collaboration model, ownership map, decision hierarchy, escalation path, and conflict resolution are defined in full in `CLAUDE.md` §18 — **deferred to here, not restated.** Operational detail on top:

- **When to use multiple skills together.** A single task usually spans layers — invoke every skill that owns a touched layer and reconcile their standards into one coherent output, never a committee transcript (`agentverse-master-ai-engineering-team` Operating Principle 6). Example: a new streaming run endpoint pulls in `api-designer` (contract), `fastapi-expert` (SSE route), `system-designer` (queue/fan-out), `redis-expert` (pub/sub), `opentelemetry-expert` (trace), and `security-reviewer` (disconnect cleanup, auth).
- **When the Master decides.** Any cross-discipline conflict or coherence question routes to `agentverse-master-ai-engineering-team` as final arbiter (`CLAUDE.md` §18.2). Discipline leads own final sign-off within their discipline; specialists own depth and escalate cross-cutting conflicts up.
- **How conflicts are resolved.** Cite the owning skill's standard, then escalate up the decision hierarchy if unresolved (specialist → discipline lead → Master). No skill invents a competing standard inside a review or PR (`CLAUDE.md` §18.6). Where a conflict was already resolved in the constitution (e.g., DRY-vs-service-isolation, the pricing ownership chain), that resolution is binding.
- **Subagent delegation.** Delegate only genuinely independent work with a self-contained brief; reconcile outputs into one consistent result. Tightly-coupled changes stay undelegated (`claude-code-expert`).

---

## 9. Context Loading Strategy

Before **any** task, load context in this exact priority order:

1. **`CLAUDE.md`** — the Engineering Constitution.
2. **Project Memory** — [`docs/project-memory.md`](./project-memory.md).
3. **Decision Log** — [`docs/decision-log.md`](./decision-log.md).
4. **AI Playbook** — this file (`docs/ai-playbook.md`).
5. **Relevant Skills** — the specific `SKILL.md` files that own the task's layers.
6. **Current Task** — the actual request, plan, and diff.

**Why this order.** The **constitution first** because it is the highest authority and every other document is subordinate to it. **Product/business context next** so the work serves a real persona/metric, not an abstract capability. **Established technical precedent (the decision log) next** so a choice already made with its trade-offs isn't silently re-litigated. **Operating procedure (this playbook) next** so the work follows the right workflow and gates. **Domain expertise (the skills) next** for the depth of the specific layers touched. **The actual task last**, interpreted through everything above it. Loading in reverse — starting from the task — is exactly how standards get missed; higher-authority, broader context always frames the narrower.

---

## 10. Prompt Engineering Standards

Prompt ownership is `prompt-engineer`'s, for both AgentVerse's own product prompts (run summaries, trace explanation, onboarding copilot) and the templates end-users compose in the agent builder (`CLAUDE.md` §4, §9). Standards are cited from there; operational guidance added here:

- **Versioning discipline.** A prompt is a versioned artifact (git history or a prompt-registry table), never an inline string literal; version IDs are immutable once shipped, and edits create a new version — so any prompt is diffable and rollback-able independent of a code deploy.
- **Eval-before-ship.** No prompt ships or changes without an eval run against its golden dataset; deterministic checks first, reference-anchored LLM-as-judge only where a quality can't be checked deterministically; cost and latency tracked per variant.
- **No prompt change without a regression check.** Editing a prompt re-runs its golden dataset as a gate; the full eval suite also re-runs whenever the target model or model version changes, not only when the prompt text changes.
- **Injection-resistant by construction.** Instructions, retrieved/tool context, and user input are always structurally delimited so downstream content can't be mistaken for instructions; user-authored builder templates inherit the same defaults. Output-format instructions specify the exact schema the consuming code expects.
- **Validated against the fallback.** A prompt tuned only against its primary model is unfinished until validated against its documented fallback (`ai-architect` routing).

---

## 11. Code Review Checklist

Usable standalone; grounded in `code-reviewer`'s Review Checklist and `CLAUDE.md` §16 Code Quality (cited, not fully restated).

- [ ] Does the code do what the PR/ticket says, with edge cases (empty input, concurrent runs, plan-tier limits) handled — not just the happy path?
- [ ] Does every path touching a tenant resource correctly propagate `workspace_id`, resolved from the authenticated identity, through every new function/query? (Rule 11)
- [ ] Are new Postgres queries parameterized (no f-string/format SQL), and do new tenant tables carry `workspace_id` with a leading index? (§8)
- [ ] Do new streaming (SSE/WebSocket) endpoints clean up their Redis subscription and background task on client disconnect? (§6, §7)
- [ ] Are new API routes under `/api/v1` with Pydantic v2 request/response models (no raw `dict`/`Any`) and the shared error envelope? (§7)
- [ ] No blocking call inside `async def`; CPU-bound work offloaded? (Rule 12)
- [ ] Tests proportional to risk are present and actually exercise the changed logic; no exact-string assertions on LLM output? (§11, Rule 4)
- [ ] Is any long-running/agent/LLM work dispatched to a worker rather than run inline? (Rule 5, Rule 14)
- [ ] Every LLM call through the provider-abstraction layer — no provider SDK imported in a route/workflow/orchestration file? (Rule 16)
- [ ] UI changes use design tokens (no raw hex/arbitrary spacing) and define empty/loading/error states with the same rigor as the populated state? (§6, §15)
- [ ] Accessibility basics: semantic HTML, keyboard operability, accessible names, no color-only status? (§15, Rule 7)
- [ ] Do error messages/logs avoid leaking secrets, tokens, or other tenants' data? (§10)
- [ ] Dead code, commented-out blocks, duplicated helpers removed/consolidated? (§16)
- [ ] Does the diff need `architecture-reviewer` (new service/datastore/cross-service call) or `security-reviewer` (auth/authz/secrets/input) routing?
- [ ] Is the PR description accurate to what the diff actually does, with a rollback note for infra/schema changes? (§14)

---

## 12. Architecture Review Checklist

Grounded in `architecture-reviewer`; standards owned by the architecture skills (`CLAUDE.md` §5).

- [ ] Does an ADR exist in `docs/adr/` in Context/Decision/Consequences format, stating alternatives considered?
- [ ] Is `workspace_id` scoping preserved through every new table, service call, and cache key the design introduces?
- [ ] Does a new capability stay in an existing service unless a concrete scaling/ownership/failure-isolation reason justifies a new one?
- [ ] Is data ownership unambiguous — exactly one service owns each entity's source-of-truth table, with no direct cross-service DB access (including "read-only" convenience)?
- [ ] Is long-running/bursty work (agent runs, batch jobs, LLM calls) routed through a queue to `apps/worker`, never inline in a request?
- [ ] Does every new synchronous inter-service call have an explicit timeout and circuit-breaker/fallback, with no chain nesting more than two levels deep?
- [ ] Are non-critical decoupled needs (usage tracking, notifications, archival) on the event stream, with versioned, schema-validated payloads (`event_type`, `schema_version`)?
- [ ] Does a feature expected to hit load state an actual estimate (RPS, concurrency, data volume), producing an approve-with-conditions verdict where appropriate?
- [ ] Does a new service define `/health` and `/ready` and own exactly one datastore?
- [ ] Does the design avoid direct vector-DB access from any service other than the `agent-runtime` fleet, and keep the frontend behind the `/api/v1` gateway?
- [ ] Is a breaking public-contract change versioned with a deprecation window, not an in-place edit?
- [ ] Are Mermaid diagrams (with trust boundaries) checked into the repo, and has `microservices-architect` reviewed any partitioning/decomposition element?

---

## 13. Security Review Checklist

Grounded in `security-reviewer`/`owasp-expert`/`secure-coding-expert`; standards owned by `security-engineer` et al. (`CLAUDE.md` §10).

- [ ] Does every new query/endpoint touching workspace data, runs, or billing derive `workspace_id`/`org_id` from the authenticated session, never from client-supplied values (IDOR)? (Rule 11)
- [ ] Deny-by-default authorization enforced server-side via the shared permission-check dependency — not just a hidden UI control — and tested cross-role and cross-workspace? (§10)
- [ ] Correct `403` (same-workspace permission gap) vs. `404` (cross-workspace, don't leak existence) semantics?
- [ ] Is all new SQL parameterized, with no raw string interpolation of untrusted input? (§10)
- [ ] Does every LLM prompt-construction path structurally isolate/delimit untrusted content (user input, tool output, RAG chunks, uploaded docs) so it can't reach instructions or tool calls (prompt injection)? (§9 Safety, §10)
- [ ] Does every agent-initiated outbound call (tool/MCP/webhook) route through the egress control point denying RFC1918/link-local/metadata/loopback (SSRF)? (§10, Rule 6)
- [ ] Are secrets read only from the secrets manager/environment — never hardcoded, logged, in error messages, client bundles, or image layers — with a missing secret failing startup loudly and `NEXT_PUBLIC_*` audited? (§10, Rule 1)
- [ ] Do streaming/WebSocket endpoints authenticate the connection and tear down the Redis subscription/background task on disconnect so they can't leak across sessions?
- [ ] Are file uploads content-sniffed (not trusting client MIME), size-capped, and stored with a generated name outside the web root? (§10)
- [ ] Do error responses avoid leaking stack traces, secrets, or other tenants' identifiers? (§7 error envelope)
- [ ] Are auth/permission grants and denials on sensitive actions written to append-only `audit_logs` from the enforcement point? (§10)
- [ ] Does a dependency change introduce a known CVE (`pip-audit`/`osv-scanner`/`npm audit`), and is this finding one-off (fix here) or systemic (escalate to `owasp-expert`)?

---

## 14. Release Checklist

Grounded in `final-qa-reviewer`; a release gate, not a re-review (`CLAUDE.md` §18.4–18.5, §19).

- [ ] Does every PR in the release have a recorded `code-reviewer` approval? (Merged ≠ signed off.)
- [ ] Does every architecturally significant change have a recorded `architecture-reviewer` verdict, or an explicit not-applicable?
- [ ] Is `security-reviewer`'s verdict clear or clear-with-follow-up (follow-up ticketed, non-blocking), with zero unresolved blocking findings?
- [ ] Was `qa-engineer`'s regression plan executed (cross-tenant isolation + billing correctness included) and are `testing-architect`'s CI gates (unit/integration/E2E) green for this exact build?
- [ ] Do release notes exist, authored/reviewed by `technical-writer`, accurately describing user-facing and breaking changes (not what was *intended* to ship)?
- [ ] Does a rollback plan exist (owned by `devops-engineer`/`deployment-engineer`) with a stated trigger and time-to-rollback?
- [ ] If the release includes a migration, is it reversible/additive at deploy time, or is a forward-only mitigation explicitly documented? (Rule 19)
- [ ] Is required CI (lint/type-check/build) green across `apps/web`, `apps/api`, `apps/worker`?
- [ ] Is monitoring in place — `/health` + `/ready` for new services, dashboards/alerts with runbooks, agent-execution observability intact? (§12, §19)
- [ ] Are any go-with-conditions items ticketed with an owner and deadline?
- [ ] Is the final go / no-go / go-with-conditions call recorded against the release ticket/changelog for future incident review?

---

## 15. AI Quality Checklist

A distinct checklist for AI-specific quality — grounded in `prompt-engineer`, `ai-architect`, and `rag-expert`; run on any change touching a prompt, agent, retrieval pipeline, or model routing (`CLAUDE.md` §4, §9, §11).

- [ ] **Prompt regression.** Did the changed prompt re-run its golden dataset (including adversarial, out-of-scope, and ambiguous cases) and pass, with results (score, cost, latency) recorded against the new version?
- [ ] **Versioning.** Is the prompt a new immutable version (not an in-place edit of a shipped one), rollback-able independent of a code deploy?
- [ ] **Hallucination / grounding.** For RAG-backed answers, do outputs carry citations (`document_id`/`chunk_id`) traceable to source, is context assembled within the model's real token budget, and is the similarity threshold justified by a labeled eval set — not a guessed constant?
- [ ] **Tenant isolation in retrieval.** Is every vector search pre-filtered by `workspace_id`, with no mixing of embedding-model versions in one query? (Rule 11; §8)
- [ ] **Cost/latency budget.** Is model routing deliberate per task type (cheap/fast for classification/tool-selection, strongest reserved for synthesis), with token usage recorded per workspace/run, and the change within its cost/latency budget?
- [ ] **Guardrail coverage.** Are guardrails derived from the agent's declared scope, versioned with it, and do they fail closed (blocked input/output stops the run with a clear trace reason)?
- [ ] **Bounded execution.** Does every reasoning loop/workflow enforce step *and* cost *and* time ceilings? (Rule 17)
- [ ] **Fallback validated.** Is the prompt/routing validated against its documented fallback model/provider, not only the primary? (§9)
- [ ] **Tool safety.** Are tool-call arguments validated against schema before execution, tool results sanitized before re-entering agent context, and every call routed through the central tool-execution boundary? (§4)
- [ ] **Eval pass rate.** Is AI output tested by structure/behavior (valid schema, tool-call shape, groundedness) — never exact text match — with quality judgment in the eval harness, not the fast pytest suite? (§11)
- [ ] **Trace completeness.** Does every orchestration step emit a trace event, forming one connected trace per run with correct parent/child nesting? (Rule 18)

---

## 16. Continuous Improvement Process

The mechanism that keeps these three documents — and their relationship to `CLAUDE.md` — alive and non-contradictory over time. This is a process, not an aspiration.

**How standards evolve.** `CLAUDE.md` is the highest authority and changes only through the same ADR + review discipline as any architectural change (`CLAUDE.md` preamble, closing note). These three docs are subordinate: when a new decision, product shift, or workflow change lands, update the affected doc **in the same PR** as the change, reviewed like code (docs-as-code, `CLAUDE.md` §13). A change that contradicts `CLAUDE.md` is rejected — the constitution is amended first (via ADR), then the subordinate docs follow.

**How decision-log entries get updated.** A decision is **never edited to reverse it** (mirroring ADR immutability, `CLAUDE.md` §13). To change a decision: set the existing entry's **Status → `Superseded`**, add a forward link to the new entry, and write a **new entry** (next number, `v1.0`) that links **back** to the one it supersedes and states what evidence changed the call. Bump `Current Version` only for a material revision of an entry that is *not* a reversal (e.g., a clarified trade-off). Each decision carries a **Review Date**; when it arrives, re-evaluate against current evidence and either reaffirm (note the review) or supersede.

**How documentation stays synchronized.** Three cross-checks, enforced in review:
1. `project-memory.md` §6 Tech Stack and `decision-log.md` must always agree — a stack change updates both, or the PR is blocked.
2. Neither subordinate doc may restate a `CLAUDE.md` rule; a reviewer replaces any such duplication with a citation (a blocking comment, per `CLAUDE.md` §13/Rule 9).
3. The Context Loading Strategy order (§9) is fixed; changing it requires explicit sign-off from `agentverse-master-ai-engineering-team`.

**How obsolete rules are identified and removed.** Evidence-driven, never trend-following (`testing-architect`, `agile-coach`): a production incident traced to a gap, a chronically-overridden gate, a superseded decision, or a Review Date reached triggers a review. `final-qa-reviewer` runs a brief retro when something slips a gate and feeds it back to the owning gate's process. When a rule in a subordinate doc becomes obsolete, it is removed with a note (or replaced by a `CLAUDE.md` citation if the constitution now covers it) — obsolete guidance is deleted, not left to rot, so engineers keep trusting the docs.

**Ownership of this process.** `claude-code-expert` owns the skills-library and build-process hygiene; `documentation-engineer` owns internal-doc synchronization; `agentverse-master-ai-engineering-team` is the final arbiter on any cross-document conflict. On any contradiction between these three docs and `CLAUDE.md`, the constitution and the Master skill decide.

---

*This playbook governs how work happens; `CLAUDE.md` governs what is correct. When they appear to conflict, `CLAUDE.md` and the Master skill `agentverse-master-ai-engineering-team` are final.*
