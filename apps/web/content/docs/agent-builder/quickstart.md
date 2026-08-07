---
title: Build and run your first agent
summary: Go from an empty workspace to an agent that answers a question, in about five minutes.
pillar: agent-builder
last_verified: "2026-08-07"
status: published
order: 1
---

An agent in AgentVerse is stored configuration: a name, a model, system instructions, and optionally tools and knowledge. You author that configuration, publish a version of it, and then run it. This guide walks the shortest path through all three.

## Prerequisites

- A workspace. You get one when you sign up.
- The `member` role or higher. `viewer` can read agents but not create or run them.

## Create the agent

The fastest route is to install one of the first-party templates and edit it, rather than starting from a blank prompt — see [Install a template](/docs/marketplace/install-a-template). To start from nothing instead:

1. Open **Agents** in the sidebar.
2. Choose **New agent**.
3. Give it a name, pick a model, and write the system instructions.

The same thing over the API:

```bash
curl -X POST \
  "$AGENTVERSE_BASE_URL/api/v1/workspaces/$WORKSPACE_ID/agents" \
  -H "Authorization: Bearer $AGENTVERSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "Release notes writer",
        "model": "gpt-4o-mini",
        "system_instructions": "You turn merged pull request titles into release notes grouped by user impact. Be concise and never invent a change that is not in the input."
      }'
```

System instructions are the single largest lever on how an agent behaves. Say what it does, what it must not do, and what its output should look like — vague instructions produce vague agents.

## Publish a version

An agent is created as a draft. Drafts cannot run: publishing is what freezes a configuration into a version, so that a run always records exactly which configuration produced it.

```bash
curl -X POST \
  "$AGENTVERSE_BASE_URL/api/v1/workspaces/$WORKSPACE_ID/agents/$AGENT_ID/publish" \
  -H "Authorization: Bearer $AGENTVERSE_API_KEY"
```

Editing a published agent creates a new version. Older versions stay readable, so a run from last month still shows the instructions it actually ran with.

## Run it

Runs are asynchronous. Submitting one returns `202 Accepted` with a run id immediately, and the work happens on a worker — an agent that calls three tools and two models is not something to hold an HTTP request open for.

```bash
curl -X POST \
  "$AGENTVERSE_BASE_URL/api/v1/workspaces/$WORKSPACE_ID/agents/$AGENT_ID/runs" \
  -H "Authorization: Bearer $AGENTVERSE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"input": "feat(api): add per-plan rate limiting\nfix(web): correct the usage meter rounding"}'
```

Send an `Idempotency-Key` on every run you trigger. Runs cost money, and without one a network retry starts a second run and bills you for both. Replaying the same key returns the original run instead.

Or from the CLI, which prints the run id on stdout and its status on stderr so `$(...)` captures exactly the id:

```bash
run_id=$(agentverse run "$AGENT_ID" "feat(api): add per-plan rate limiting")
```

## Expected result

`GET .../runs/{run_id}` reports the run's status, and the streaming endpoint shows each step as it happens — see [Watch a run happen](/docs/observability/watch-a-run). A completed run carries its output, the steps it took, and the tokens it spent.

## Troubleshooting

**The run finishes immediately with an error about the agent not being published.** Drafts cannot run. Publish a version first.

**The run is queued and stays queued.** Queued means no worker has claimed it yet. If it persists, check your workspace's usage against its quota under **Billing** — a workspace over quota stops accepting new runs rather than silently running them for free.

**A tool you configured was ignored.** Only tools the platform recognises are attached. See [Give an agent tools](/docs/agent-builder/tools) for the list.

## Related guides

- [Give an agent tools](/docs/agent-builder/tools)
- [Ground an agent in your documents](/docs/agent-builder/knowledge-bases)
- [Install a template](/docs/marketplace/install-a-template)
