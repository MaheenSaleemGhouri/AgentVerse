# ADR 0009: Multi-Agent Teams — Topologies, Handoffs, and Shared Memory

## Status

Accepted. Implements `docs/roadmap.md` **Phase 9** (Multi-Agent Orchestration & Model Routing).

> **Numbering note.** This work was requested as "Phase 6". The roadmap's Phase 6 is *Tool-Calling, Tool-Execution Boundary & MCP*; multi-agent orchestration is Phase 9. The implementation matches the request; the label follows the roadmap so the repo's own sequencing stays coherent. Phase 6 (MCP) remains unbuilt.

## Context

Phase 4 shipped a single agent with tools: one `Agent`, one `Runner.run_streamed`, one trace. Phase 9 adds teams of agents that collaborate — supervisor delegation, planner/executor/critic, sequential chains, parallel fan-out.

Four decisions had to be settled before any code, because each has a wrong answer that produces no error at all.

**1. Do teams redefine agents, or reuse them?**

A team needs per-agent instructions, model, tools, and knowledge. All of that already exists on `agents`/`agent_versions`.

**2. What crosses an agent boundary?**

The convenient implementation passes the running conversation. The roadmap names this as one of the phase's highest risks.

**3. Where does "shared memory" live?**

Phase 5 put a vector store (`kb_chunks`) in the primary Postgres. Team memory is also "things the system remembers".

**4. How much of the orchestration do we write ourselves?**

The OpenAI Agents SDK already implements handoffs, sessions, guardrails, streaming, and tracing.

## Decision

### Teams compose agents; they never redefine them

`team_members.agent_id` is a foreign key to `agents` with `ON DELETE RESTRICT`. A team member is a *seat*, carrying only team-level facts: `role`, `position`, `handoff_description`, `can_receive_handoff`. Everything about how the agent behaves comes from its own published version.

Consequences: attaching an agent to a team changes nothing about it; improving an agent improves every team using it; and there is exactly one place agent configuration lives (Rule 3). `RESTRICT` rather than `CASCADE` because deleting an agent a team depends on should fail loudly, not silently leave a team that cannot run its own declared topology.

`role` is a team-level assignment rather than an agent property, so the same agent can be a worker in one team and the critic in another without duplication.

### Handoffs carry a typed contract, never a transcript

Every transfer of control writes a `handoffs` row whose `contract` column holds a versioned `HandoffContract`: a summary, structured findings, and *pointers* (session id, originating agent, upstream handoff id) — never raw conversation history.

Three reasons, in order of importance: an agent must never silently mutate another's context (CLAUDE.md §4); a full transcript compounds token cost at every hop; and a typed payload is inspectable in the UI, whereas a transcript dump is only readable.

`handoff_kind` distinguishes `automatic` (the SDK's own model-driven `handoff()` tool call) from `manual`/`conditional`/`parallel` (AgentVerse's orchestration layer choosing). "The model decided this" and "the topology dictated this" are different facts when debugging.

### Shared memory is relational and strictly separate from RAG

`shared_memory` is a Postgres table keyed by `(team_id, session_id, agent_id, key)`, holding JSONB values. It is **not** vector-backed and shares nothing with `kb_chunks`.

This is the roadmap's named highest-risk mistake, and the separation is structural rather than conventional: team memory is *structured state written and read by key* ("the plan", "findings so far"), while RAG is *unstructured text retrieved by similarity*. They have different access patterns, different lifecycles, and different correctness criteria. Putting them in one store would let "what an agent remembers" and "what a document says" contaminate each other in both directions — corrupting retrieval quality and grounding simultaneously, with no error raised.

`scope` (`team` / `session` / `agent`) is stored per entry rather than inferred, so widening access is an explicit, auditable write.

### The SDK owns orchestration mechanics; AgentVerse owns policy

Pinned at `openai-agents>=0.18.3`. We use the SDK's `Agent`, `Runner`, `handoff()`, `Session` protocol, `InputGuardrail`/`OutputGuardrail`, streaming, and tracing, and we reimplement none of them.

The division is: **the SDK decides how control transfers; AgentVerse decides who is reachable, what bounds apply, and what gets recorded.**

Concretely, per topology:

| Topology | SDK construction |
| --- | --- |
| `supervisor_worker` | One supervisor `Agent` with `handoffs=[...]` targeting each worker. The SDK's own delegation runs the show. |
| `planner_executor_critic` | Three `Runner` invocations in sequence, each fed the previous stage's typed contract. |
| `sequential` | `Runner` per member in `position` order, chained by contract. |
| `parallel` | `asyncio.gather` over per-member `Runner` calls, then an aggregator merges. |

Shared memory is exposed to agents as SDK **function tools** (`remember` / `recall`), not as prompt stuffing — so a write is an auditable tool call, not a side effect buried in generated text.

Conversation state uses a Postgres-backed implementation of the SDK's `Session` protocol (`get_items` / `add_items` / `pop_item` / `clear_session`). The SDK's default is in-memory; on a multi-instance worker fleet that silently loses state when a follow-up lands on a different instance.

### Bounds are per team, and all three are required

`max_turns`, `max_cost_micro_usd`, and `timeout_seconds` are columns on `teams`, not global constants. A loop under the step limit can still be a cost incident, and one under both can still hang on wall-clock (Rule 17). They are per team because a research team and a triage team have legitimately different ceilings.

`max_turns` maps to the SDK's own `Runner` turn limit rather than a hand-rolled counter; cost and time are checked by AgentVerse, which the SDK has no notion of.

## Consequences

- Eight new tables; `execution_events` and `team_session_items` are partitioned by `created_at` from their first migration, matching `agent_run_steps`.
- The eighth table, `team_session_items`, was added during implementation rather than designed here, and is called out so the gap is visible: the SDK `Session` protocol needs somewhere to keep conversation items, and neither of the two tables that superficially fit was right. `execution_events` would mix SDK-internal state into the trace stream the UI renders (and make `pop_item` a delete against a partitioned trace table); `communication_logs` would pollute its typed inter-agent vocabulary with raw model items. Conversation history is its own concern with its own lifecycle. Its `id` is a Postgres identity column rather than a UUID because it carries ordering as well as identity — deriving order from a writer-computed sequence would race between concurrently running members.
- `uq_shared_memory_scope_key` is declared `UNIQUE NULLS NOT DISTINCT` (Postgres 15+; this stack pins pg16). `session_id` and `agent_id` are null for team-scoped entries, and the default UNIQUE treats every NULL as distinct — which would silently turn the upsert into an append for exactly the widest-shared scope, with no error raised.
- Sessions are branched per member, keyed `(session_id, agent_id)`, with a null-`agent_id` branch for the orchestrator. Merging members into one history would hand each of them the others' partial reasoning; what crosses between branches is a `HandoffContract`, never raw items.
- `team_sessions` is its own table rather than a row in `agent_runs`, which requires a single `agent_version_id` — a team session has no single version, and inventing one would misreport what produced the result.
- `execution_events.event_type` is free-form text, not an enum: the vocabulary grows per topology, and adding an event type must never require a migration. The frontend's exhaustive union is the enforcement point.
- Deleting an agent that belongs to a team now fails with a foreign-key error. That is intended, and the API surfaces it as a 409 naming the blocking teams.
- Two things in the product are called "team". `/dashboard/{ws}/team` is workspace membership (humans, RBAC); `/dashboard/{ws}/teams` is AI teams. They share no table, route, or repository.

## Alternatives considered and rejected

- **Duplicate agent config onto team members** so a team is self-contained. Rejected: two definitions of the same agent drift, and the drift is silent.
- **Store handoff payloads as raw transcript** "just for the first version". Rejected outright — it is the exact silent-context-mutation risk CLAUDE.md §4 rules out, and "just this once" is how it becomes permanent.
- **Vector-backed shared memory in `kb_chunks` with a `namespace` column.** Rejected: a shared table with a discriminator column is one forgotten `WHERE` away from cross-contamination, and the access patterns are not similar enough to justify the shared risk.
- **Hand-rolled orchestration loop** instead of SDK handoffs. Rejected: it would reimplement handoff, session, and guardrail behavior the SDK already provides, and the user's brief explicitly forbids recreating SDK functionality.
- **One global bound for every team.** Rejected: any single value is either too tight for real research work or too loose to protect against a runaway triage agent.
