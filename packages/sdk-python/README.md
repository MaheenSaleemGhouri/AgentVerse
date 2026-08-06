# agentverse (Python SDK)

Official Python client for the AgentVerse API.

```bash
pip install agentverse
```

```python
from agentverse import AgentVerse

with AgentVerse() as av:                     # AGENTVERSE_API_KEY, AGENTVERSE_WORKSPACE_ID
    agent = av.marketplace.install("research-assistant")
    run = av.runs.create(agent_id=agent["agent_id"], input="Summarise this document.")
    print(run["id"], run["status"])
```

Async is the same surface with `await`:

```python
from agentverse import AsyncAgentVerse

async with AsyncAgentVerse() as av:
    agents = await av.agents.list()
```

## Verifying webhooks

The part worth using rather than reimplementing — constant-time
comparison, timestamp tolerance, and verification over the raw bytes:

```python
from agentverse.webhooks import verify_webhook, SignatureVerificationError

try:
    event = verify_webhook(
        payload=raw_request_body,            # bytes, not a parsed dict
        signature_header=headers["AgentVerse-Signature"],
        secret=os.environ["AGENTVERSE_WEBHOOK_SECRET"],
    )
except SignatureVerificationError:
    return 400
```

Passing a re-serialized dict instead of the raw body is the most common
way to break this: the signature is over bytes, and a JSON library that
spaces its output differently produces a different digest for an
identical object.

## Retries

Reads retry on 408/429/5xx with exponential backoff and full jitter, and
a server's `Retry-After` always wins over the client's own guess.

Mutations retry **only** when they carry an `Idempotency-Key` — otherwise
a retried POST that already arrived would duplicate it. `runs.create()`
generates one for you, because a run costs money.

## Status

Built and tested in this repository; **not yet published to PyPI**.
Install from source:

```bash
pip install ./packages/sdk-python
```
