---
title: Give an agent tools
summary: Attach built-in tools, or connect an external service over MCP, and control what the agent is allowed to call.
pillar: agent-builder
last_verified: "2026-08-07"
status: published
order: 2
---

A tool is something an agent can call while it is running: a calculation, a lookup, an action in another system. Without tools an agent can only produce text from what it already knows. With them it can act.

## Prerequisites

- An agent you can edit (`member` or higher).
- For MCP tools, the `admin` role — connecting an external service means storing credentials for it.

## Built-in tools

Two tools ship with the platform and need no configuration:

| Tool | What it does |
| --- | --- |
| `get_current_time` | The current time, so an agent stops guessing dates. |
| `calculator` | Arithmetic, so an agent stops doing it in its head. |

Name them in the agent's `tools` list:

```json
{
  "name": "Invoice checker",
  "model": "gpt-4o-mini",
  "system_instructions": "Check the arithmetic on invoices. Use the calculator tool for every sum rather than computing it yourself.",
  "tools": ["calculator", "get_current_time"]
}
```

A tool name the platform does not recognise is rejected when you save, not silently dropped at runtime. That is deliberate: an agent that quietly runs without the tool you configured produces plausible answers with none of the grounding you asked for.

## Connect an external service over MCP

Anything beyond the built-ins comes from an MCP server — the open protocol AgentVerse uses to talk to external tools. Open **Integrations** in the sidebar to register one.

Two things are worth knowing before you connect one:

**Credentials never live in the agent's configuration.** They are stored encrypted and resolved at call time, so exporting or publishing an agent never carries its secrets with it.

**Tool descriptions are part of the prompt.** The description an MCP server gives a tool is what the model reads when deciding whether to call it. A vague description ("does stuff with data") degrades tool selection exactly as much as a vague system prompt would.

## What happens when a tool fails

A failing or unreachable MCP server disables only its own tools for that run and records why in the trace. The run continues without them rather than crashing — but the agent will be working without a capability you expected it to have, which is why the trace says so explicitly.

Every tool call, including refused ones, is recorded. Open **MCP** in the sidebar for the full history across your integrations.

## Expected result

Running the agent produces a trace with a step per tool call, showing the arguments the model chose and what came back.

## Troubleshooting

**The agent never calls the tool.** Almost always the description or the system instructions. Say explicitly when the tool should be used ("use the calculator for every sum") rather than assuming the model will infer it.

**A tool call was refused.** Tool arguments produced by a model are untrusted input and are validated against the tool's schema before anything executes. A refusal means the arguments did not match the schema — the trace records the call and the reason.

## Related guides

- [Build and run your first agent](/docs/agent-builder/quickstart)
- [Read a run's trace](/docs/observability/watch-a-run)
