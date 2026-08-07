---
title: Watch a run happen and read its trace
summary: Stream a run's steps live, then read the finished trace to see every tool call, model call, and cost.
pillar: observability
last_verified: "2026-08-07"
status: published
order: 1
---

Every run produces one connected trace covering the whole path — the API request, the orchestration decisions, each tool call, each model call. When an agent does something surprising, the trace is where you find out why.

## Prerequisites

- A run id. See [Build and run your first agent](/docs/agent-builder/quickstart).
- `viewer` or higher.

## Stream it live

The run stream is a Server-Sent Events endpoint. Each event is a step as it happens:

```bash
curl -N \
  "$AGENTVERSE_BASE_URL/api/v1/workspaces/$WORKSPACE_ID/agents/$AGENT_ID/runs/$RUN_ID/stream" \
  -H "Authorization: Bearer $AGENTVERSE_API_KEY"
```

In the product, **Playground** streams a run against a published agent and shows the same steps as they arrive.

Streaming is the only way to see a run in progress. A run that is still going has produced steps that a status poll will not show you.

## Read the trace

Every orchestration step emits a trace event: model calls with their token usage, tool calls with the arguments the model chose and what came back, retrieval with the chunks it pulled, and handoffs between agents in a team. Steps nest — a tool call sits under the model call that decided to make it — so the trace reads as the shape of what happened rather than a flat log.

## Cost

Each model call records its token usage, attributed to the workspace and the run. A run's cost is the sum of its calls, which means an expensive run can be traced to the specific step that made it expensive — usually one retrieval pulling far more context than the answer needed, or a loop repeating a call.

## Tool-call history

**MCP** in the sidebar lists tool calls across every integration, including refused ones. A refused call is recorded with its reason: tool arguments produced by a model are validated against the tool's schema before anything executes, and a refusal is that validation doing its job.

## Audit logs

Traces record what agents did. **Audit logs** record what *people* did: sign-ins, permission changes, destructive actions. The log is append-only — entries cannot be edited or removed, including by an admin. `admin` or higher to read it.

## Expected result

For any run: the steps it took, in order and nested, with what each one cost.

## Troubleshooting

**The stream ends with nothing.** The run had already finished. Streams carry steps as they happen; use the run detail for a finished run.

**A step shows a tool call that was refused.** Schema validation rejected the arguments the model produced. The trace records both.

**The run stopped without an error.** It hit a ceiling — steps, cost, or wall-clock. The trace names which one. Ceilings are enforced on every run precisely so an unbounded loop is a stopped run rather than an invoice.

## Related guides

- [Give an agent tools](/docs/agent-builder/tools)
- [Build a team of agents](/docs/orchestration/teams)
