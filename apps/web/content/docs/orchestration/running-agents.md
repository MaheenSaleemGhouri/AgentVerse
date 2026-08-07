---
title: Run an agent from your own code
summary: Trigger runs over the REST API, the Python and TypeScript SDKs, or the CLI — and retry them safely.
pillar: orchestration
last_verified: "2026-08-07"
status: published
order: 1
---

Everything the dashboard does, it does over the same public API you have. This guide covers triggering a run from outside the product.

## Prerequisites

- A workspace-scoped API key — see [API keys and the SDKs](/docs/platform/api-keys-and-sdks).
- A published agent.

## Runs are asynchronous

`POST .../runs` returns `202 Accepted` with a run id and a status URL. It does not wait for the agent to finish. An agent that calls several tools and a model or two can take minutes, which is not something to hold an HTTP connection open for, and a client that assumes otherwise will time out on exactly its most useful runs.

## Trigger a run

```python
from agentverse import AgentVerse

with AgentVerse() as client:  # reads AGENTVERSE_API_KEY and AGENTVERSE_WORKSPACE_ID
    run = client.runs.create(
        agent_id="agt_...",
        input="Summarise this week's merged pull requests.",
    )
    print(run["id"], run["status"])
```

```typescript
import { AgentVerse } from "@agentverse/sdk";

const client = new AgentVerse();
const run = await client.runs.create({
  agentId: "agt_...",
  input: "Summarise this week's merged pull requests.",
});
console.log(run.id, run.status);
```

```bash
agentverse run agt_... "Summarise this week's merged pull requests."
```

## Idempotency

Run-triggering endpoints accept an `Idempotency-Key` header, and you should always send one. Replaying the same key returns the original run rather than starting another. Without it, a client that retries on a timeout — which is the normal thing for a client to do — starts a second run and pays for both.

Both SDKs send one automatically for run creation. If you are calling the API directly, generate a UUID per logical run and reuse it across that run's retries.

## Retries and rate limits

The SDKs retry idempotent requests on `408`, `429`, `500`, `502`, `503` and `504`, with exponential backoff and full jitter, honouring `Retry-After` when the server sends it. They do **not** retry non-idempotent requests that lack an idempotency key — silently repeating a billable action is not a helpful default.

Rate limits are per workspace and per API key, and vary by plan. Exceeding one returns `429` with a `rate_limited` code and a `Retry-After` header.

## Expected result

A run id you can poll or stream. See [Watch a run happen](/docs/observability/watch-a-run).

## Troubleshooting

**`202` but the run never starts.** Check usage against quota under **Billing**. A workspace over its quota stops accepting runs.

**`429` immediately.** You are over your plan's per-minute limit. Back off for the interval in `Retry-After`; the SDKs do this for you.

**Two runs where you expected one.** A retry without an `Idempotency-Key`.

## Related guides

- [API keys and the SDKs](/docs/platform/api-keys-and-sdks)
- [Watch a run happen](/docs/observability/watch-a-run)
- [Receive webhooks](/docs/platform/webhooks)
