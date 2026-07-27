# Multi-Agent Teams

How AgentVerse runs several agents together. Implements `docs/roadmap.md`
Phase 9; the decisions behind it are in
[ADR-0009](../adr/0009-multi-agent-teams-topologies-and-shared-memory.md).

> **Naming.** Two things in the product are called "team".
> `/dashboard/{ws}/team` is workspace membership — humans and RBAC roles.
> `/dashboard/{ws}/teams` is teams of *agents*. They share no table,
> route, or repository. The sidebar labels the first one "Members" for
> exactly this reason.

## What a team is

A team is a stored composition of **existing agents** plus a topology. A
team member is a *seat*: it points at an `agents.id` and carries only
team-level facts (`role`, `position`, `handoff_description`,
`can_receive_handoff`). Everything about how an agent behaves — its
instructions, model, tools, knowledge bases — comes from its own
published version.

Consequences worth stating plainly:

- Attaching an agent to a team changes nothing about that agent.
- Improving an agent improves every team using it.
- The same agent can be a worker on one team and the critic on another.
- Deleting an agent a team depends on **fails** (`ON DELETE RESTRICT`),
  surfaced by the API as a 409 naming the blocking teams.
- A member whose agent has no published version is skipped at run time.
  The builder says so before you run, rather than letting you find out
  from a failed session.

## Topologies

| Topology | What it does | SDK construction |
| --- | --- | --- |
| `supervisor_worker` | A supervisor decides who to delegate each part to | One supervisor `Agent` with `handoffs=[...]`; the SDK's own delegation runs it |
| `sequential` | Members run in `position` order, each fed the previous one's contract | One `Runner.run` per member, chained by contract |
| `planner_executor_critic` | Plan, do, review | Three `Runner.run` calls, chained by contract |
| `parallel` | Members work the same task at once, an aggregator merges | `asyncio.gather` over per-member `Runner.run`, then an aggregator stage |

The set is closed and exhaustively dispatched — an unrecognised topology
aborts the session with a stated reason rather than silently falling back
to something plausible.

`planner_executor_critic` requires all three seats and fails loudly when
one is missing: degrading to two stages would produce unreviewed output
from a topology whose entire value is the review.

## What crosses an agent boundary

Never a transcript. Every transfer of control writes a `handoffs` row
whose `contract` column holds a versioned `HandoffContract`
(`packages/python-shared/.../teams/handoff_contract.py`):

```json
{
  "schema_version": 1,
  "summary": "Found three competitor tiers on the pricing page.",
  "session_id": "…",
  "from_agent_id": "…",
  "to_agent_id": "…",
  "next_task": "Draft the comparison table.",
  "findings": [{ "label": "Tiers", "detail": "Free, Pro, Enterprise" }],
  "memory_keys": ["research_findings"],
  "source_document_ids": ["…"],
  "upstream_handoff_id": "…"
}
```

Bulk context is passed as *pointers* — `memory_keys` to `recall()`,
`source_document_ids` to retrieve — so the receiver decides what to load
rather than paying for whatever the sender happened to have open.

Three reasons, in order of weight:

1. An agent must never silently mutate another's context (CLAUDE.md §4).
   A transcript hands the receiver everything the sender saw, including
   any injected instruction that reached it — so one compromised member
   compromises the team.
2. A transcript compounds token cost at every hop.
3. A typed payload renders in the Collaboration Timeline. A transcript
   dump can only be read.

When a contract is rendered into the receiving agent's input, it is
wrapped in `<handoff>` delimiters behind an explicit "reported
information, not instructions" preamble. Everything inside came from
another model's output and is treated as untrusted content, exactly like
a retrieved document.

### `handoff_kind`

| Kind | Means |
| --- | --- |
| `automatic` | The supervisor model chose to delegate, via the SDK's own `handoff()` tool call |
| `manual` | The topology moved to the next stage |
| `conditional` | A configured condition routed it |
| `parallel` | A parallel branch finished and reported back |

"The model decided this" and "the topology dictated this" are different
facts, and which one happened is the first question asked when a team
routes badly. The UI shows the kind rather than collapsing them into a
generic "handoff" chip.

## Shared memory

`shared_memory` is a Postgres table keyed by
`(team_id, session_id, agent_id, key)` holding JSONB values. It is
**not** vector-backed and shares nothing with Phase 5's `kb_chunks`.

The separation is structural rather than conventional: team memory is
structured state written and read by key ("the plan", "findings so far"),
while RAG is unstructured text retrieved by similarity. Different access
patterns, different lifecycles, different correctness criteria. One store
with a discriminator column would be one forgotten `WHERE` from letting
"what an agent remembers" and "what a document says" contaminate each
other — in both directions, with no error raised.

Agents reach it as SDK **function tools**, not prompt stuffing:

| Tool | Does |
| --- | --- |
| `remember(key, value, scope)` | Upserts an entry |
| `recall(key)` | Reads at the narrowest scope visible to the caller |
| `list_memory_keys()` | Lists readable keys, so a member does not burn turns guessing |

Every access is therefore an auditable tool call, not a side effect
buried in generated text. The agent's identity is closed over at tool
construction — never a tool parameter — because tool arguments come from
the model, and letting it name whose memory it is writing would hand it
the ability to write as another member.

### Scopes

| Scope | Readable by | `session_id` | `agent_id` |
| --- | --- | --- | --- |
| `team` | every member, every session | null | null |
| `session` | every member, this session only | set | null |
| `agent` | only the writing agent | set | set |

Reads resolve narrowest-first, so an agent's own note shadows the team's.
With `shared_memory_enabled = false`, every write collapses to `agent`
scope and members cannot read each other.

> The unique constraint is `UNIQUE NULLS NOT DISTINCT`. Postgres's
> default treats every NULL as distinct, which would silently turn the
> upsert into an append for exactly the widest-shared scope.

## Conversation state

`PostgresTeamSession` implements the Agents SDK `Session` protocol
(`get_items` / `add_items` / `pop_item` / `clear_session`) against
`team_session_items`. The SDK's shipped sessions are in-memory and
SQLite; on a multi-instance worker fleet both silently lose state when a
follow-up turn lands on a different instance.

Two properties matter:

- **One DB transaction per protocol call**, never one held across a
  `Runner` turn — that would pin a pooled connection for the duration of
  an LLM request.
- **One branch per member**, keyed `(session_id, agent_id)`, with a
  null-`agent_id` branch for the orchestrator. A parallel topology runs
  members concurrently; merging their turns would hand each of them the
  others' partial reasoning. What crosses between branches is a
  `HandoffContract`.

## Bounds

`max_turns`, `max_cost_micro_usd`, and `timeout_seconds` are columns on
`teams`, not global constants — a research team and a triage team have
legitimately different ceilings. **All three are required** (Rule 17): a
loop under the turn limit can still be a cost incident, and one under
both can still hang on wall-clock.

- `max_turns` maps to the SDK's own `Runner` turn limit, fed each
  stage's *remaining* budget — otherwise a four-stage chain could spend
  the whole ceiling on stage one and still look "within bounds" at every
  individual call.
- Cost is summed from the SDK's reported usage after every stage and
  checked before the next one starts.
- The wall-clock ceiling wraps the whole topology via `asyncio.timeout`,
  not each stage — the user waits for the session, not for a stage.

Cost and turns are recorded on failure too. A session that aborted on its
cost ceiling has by definition spent money; writing null there would hide
the very incident the ceiling exists to catch.

## Execution flow

```
POST /teams/{id}/sessions          (API, 202 Accepted)
  ├─ validate runnable             members exist, ≥1 published
  ├─ idempotency check + lock      replay returns the original session
  ├─ INSERT team_sessions          row first…
  └─ enqueue team_session job      …then the job
                                        │
apps/worker: handle_team_session_job    ▼
  ├─ terminal already? → return          (redelivery is a no-op)
  ├─ load team + published members
  ├─ status = running, emit session_started
  ├─ asyncio.timeout(team.timeout_seconds)
  │    └─ execute_topology(…)
  │         ├─ build SDK Agents (+ shared-memory tools, + handoffs)
  │         ├─ Runner.run per stage, on its own PostgresTeamSession branch
  │         ├─ account cost + turns, enforce bounds
  │         └─ write handoffs / communication_logs / execution_events
  └─ status = success|error, emit session_completed|session_failed
```

Every trace event is both persisted to `execution_events` and published
to `team_session:{session_id}:events`, in the **same shape** — so a live
subscriber and a client backfilling after a reconnect see one
representation of what happened, not two that can drift.

## API

All under `/api/v1/workspaces/{workspace_id}/teams`. `workspace_id` comes
from the authenticated identity, never the path parameter.

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `` | member | |
| `GET` | `` | viewer | |
| `GET` | `/{id}` | viewer | 404 across workspaces, never 403 |
| `PATCH` | `/{id}` | member | `exclude_unset` — null clears, omitted leaves alone |
| `POST` | `/{id}/duplicate` | member | Copies config + seats, not history |
| `DELETE` | `/{id}` | admin | Soft; sessions stay readable |
| `POST` | `/{id}/members` | member | 409 if the agent is already a member |
| `DELETE` | `/{id}/members/{mid}` | member | |
| `PUT` | `/{id}/members/order` | member | Full list required; partial is a 400 |
| `POST` | `/{id}/sessions` | member | `202`, honours `Idempotency-Key` |
| `GET` | `/{id}/sessions` | viewer | Cursor-paginated |
| `GET` | `/{id}/sessions/{sid}` | viewer | |
| `GET` | `/{id}/sessions/{sid}/events` | viewer | Paged by `after_sequence` |
| `GET` | `/{id}/sessions/{sid}/handoffs` | viewer | |
| `GET` | `/{id}/sessions/{sid}/communications` | viewer | |
| `GET` | `/{id}/sessions/{sid}/stream` | viewer | SSE |
| `GET` | `/{id}/analytics` | viewer | Integer micro-USD |

A partial reorder is rejected rather than applied: omitted members left
at stale positions would silently change what a `sequential` team runs
when.

## Frontend

| Screen | Route |
| --- | --- |
| AI Teams | `/dashboard/{ws}/teams` |
| Team Details (roster · run · sessions · settings) | `/dashboard/{ws}/teams/{teamId}` |
| Session (runtime · collaboration · messages) | `/dashboard/{ws}/teams/{teamId}/sessions/{sessionId}` |

Built from the existing AVDS primitives — no new component library, and
no screen redefines a status colour. Notable behaviour:

- **Runtime Monitor** extends the single-agent monitor's model with
  running members, handoff count, and per-member attribution. Exhaustive
  over the event union with a `never` check, so a new event type fails
  the build until handled. `unknown_event` is the one deliberate escape
  hatch — an older frontend against a newer API labels what it cannot
  render rather than dropping it.
- **Reordering** is optimistic, with explicit move-up/move-down buttons
  alongside drag. Keyboard parity is select-then-act, not arrow-key drag
  emulation (CLAUDE.md §15).
- **Live vs finished**: a session in flight is fed from SSE; a finished
  one reads `execution_events` through the same narrowing function. A
  finished session never opens a stream that will never receive anything.
- The builder shows what the team still needs before it can run, mirroring
  the executor's own preconditions — so the user sees the requirement
  before submitting, not from a failed session.

## Testing

| Layer | Where | Covers |
| --- | --- | --- |
| Contract unit | `packages/python-shared/tests/teams/` | Bounds, round-trip, rolling-deploy tolerance, prompt delimiting |
| Topology unit | `apps/worker/tests/teams/test_topologies.py` | Stage order, contract chaining, handoff kinds, bounds, tracing (`Runner` faked) |
| Job unit | `apps/worker/tests/teams/test_team_session_job.py` | Status transitions, idempotency, wall-clock ceiling, failure paths |
| Integration | `apps/worker/tests/teams/integration/` | Real Postgres: session ordering/branching, memory scopes + upsert, published-member join |
| API route | `apps/api/tests/orchestration_service/interface/test_teams_route.py` | Status codes, tenancy, reorder validation, runnability guards |
| API use case | `apps/api/tests/orchestration_service/application/test_execute_team.py` | Lock contention, idempotency, enqueue ordering |
| Frontend | `apps/web/lib/hooks/useTeamSessionStream.test.ts` | Buffering, active-agent tracking, cleanup, unknown events |

The LLM is never called. `Runner` is the one SDK surface the tests
substitute; `Agent`, `handoff()`, and the session protocol are real.
