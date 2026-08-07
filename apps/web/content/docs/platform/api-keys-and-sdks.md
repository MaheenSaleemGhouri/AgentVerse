---
title: API keys and the SDKs
summary: Issue a workspace-scoped key, then call AgentVerse from Python, TypeScript, or the CLI.
pillar: platform
last_verified: "2026-08-07"
status: published
order: 1
---

Everything in the product is available over the public REST API. The SDKs and CLI are thin wrappers over it, so anything you can do in one you can do in all of them.

## Issue an API key

1. Open **Settings → API keys**.
2. Create a key and give it a name that says what will use it.
3. Copy it. It is shown once.

Keys are scoped to one workspace at issue time and stored hashed — nobody, including support, can read yours back. If you lose it, revoke it and issue another.

`admin` or higher to issue or revoke.

## Install

```bash
pip install agentverse
```

```bash
npm install @agentverse/sdk
npm install -g @agentverse/cli
```

## Configure

Both SDKs and the CLI read the same environment variables:

| Variable | Required | Meaning |
| --- | --- | --- |
| `AGENTVERSE_API_KEY` | yes | The key you issued. |
| `AGENTVERSE_WORKSPACE_ID` | yes | Which workspace to act in. |
| `AGENTVERSE_BASE_URL` | no | Override the API host. |

Check what is resolved without printing the key:

```bash
agentverse whoami
```

`whoami` deliberately never prints the key itself — it is exactly the command someone runs while sharing a screen, and printing credentials puts them in shell history and recordings.

## Use it

```python
from agentverse import AgentVerse, AsyncAgentVerse

with AgentVerse() as client:
    for agent in client.agents.list():
        print(agent["id"], agent["name"])
```

```typescript
import { AgentVerse } from "@agentverse/sdk";

const client = new AgentVerse();
const agents = await client.agents.list();
```

Both SDKs ship sync and async clients with the same surface. Use the context manager (or `close()`) — an unclosed client leaks a connection pool, which in a long-lived process is a slow file-descriptor leak rather than an obvious failure.

## CLI

```bash
agentverse agents list
agentverse templates
agentverse install research-assistant --name "Our researcher"
agentverse run agt_... "Summarise this."
agentverse webhooks events
```

Every command accepts `--json`. `run` and `install` print the id on stdout and the human-readable status on stderr, so `$(agentverse run ...)` captures exactly the id.

## Errors

Errors map to typed exceptions — authentication, permission, not-found, validation, rate-limit, quota, server — rather than raw status codes, so you can branch on the case rather than the number. Every error carries the request id from the response, which is what to quote in a support conversation.

## Retries

Idempotent requests are retried on `408`, `429`, `500`, `502`, `503` and `504` with exponential backoff and full jitter, honouring `Retry-After`. Non-idempotent requests without an idempotency key are not retried, because silently repeating a billable action is not a safe default.

## Rate limits

Per workspace and per API key, varying by plan. Over the limit returns `429` with `rate_limited` and a `Retry-After` header.

## Troubleshooting

**`ConfigurationError` on startup.** A required variable is unset. Run `agentverse whoami`.

**`401`.** The key is wrong or revoked. Keys cannot be read back — issue a new one.

**`404` on a resource you can see in the dashboard.** Almost always the wrong `AGENTVERSE_WORKSPACE_ID`. A resource in another workspace answers 404, not 403, so that workspaces cannot be enumerated.

## Related guides

- [Run an agent from your own code](/docs/orchestration/running-agents)
- [Receive webhooks](/docs/platform/webhooks)
