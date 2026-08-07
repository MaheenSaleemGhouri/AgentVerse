---
title: Receive webhooks
summary: Subscribe to platform events, verify a delivery's signature, and handle retries safely.
pillar: platform
last_verified: "2026-08-07"
status: published
order: 2
---

Webhooks push events to your endpoint as they happen, so you do not have to poll for a run that might take minutes.

## Prerequisites

- An HTTPS endpoint you control.
- `admin` or higher.

## Events

| Event | Fired when |
| --- | --- |
| `run.completed` | A run finished successfully. |
| `run.failed` | A run failed. |
| `agent.published` | A new agent version was published. |
| `billing.quota_exceeded` | A workspace crossed its usage quota. |
| `billing.subscription_changed` | A subscription changed plan or status. |
| `marketplace.listing_approved` | One of your listings was approved. |
| `marketplace.listing_installed` | Someone installed one of your listings. |

```bash
agentverse webhooks events
```

## Register an endpoint

```python
from agentverse import AgentVerse

with AgentVerse() as client:
    endpoint = client.webhooks.create(
        url="https://example.com/hooks/agentverse",
        events=["run.completed", "run.failed"],
        description="Production run notifications",
    )
    secret = endpoint["secret"]  # store this
```

An endpoint must subscribe to at least one event — an empty list is refused rather than quietly created as an endpoint that never fires.

The signing secret is returned when you create the endpoint and is readable afterwards, unlike an API key: you need it to configure your verifier.

## Verify the signature

Every delivery carries an `AgentVerse-Signature` header:

```text
t=1800000000,v1=53e42645290d85bfbc1615823cb3bcb7a956c8b7c1ce9d2704a9de4337136e56
```

Both SDKs verify it for you:

```python
from agentverse.webhooks import verify_webhook

event = verify_webhook(
    payload=request.body,                       # raw bytes
    signature_header=request.headers["AgentVerse-Signature"],
    secret=WEBHOOK_SECRET,
)
```

```typescript
import { verifyWebhook } from "@agentverse/sdk";

const event = verifyWebhook({
  payload: rawBody,
  signatureHeader: request.headers["agentverse-signature"],
  secret: process.env.WEBHOOK_SECRET,
});
```

**Verify the raw bytes, not a re-serialized object.** The single most common integration mistake is parsing the body and re-encoding it before verifying. The signature is over the exact bytes we sent, and `JSON.stringify(JSON.parse(x))` is not always `x`. Capture the raw body before any JSON middleware touches it.

Verification also rejects deliveries whose timestamp is outside a five-minute window in either direction, which is what stops a captured delivery being replayed later.

The header can carry more than one `v1=` digest during a secret rotation — a verifier that reads only the first will reject half of your deliveries during exactly the window rotation exists to make safe. Both SDKs check all of them.

## Retries and idempotency

A delivery that fails is retried up to six times with increasing backoff, over roughly two hours. `4xx` responses other than `408` and `429` are treated as final — if your endpoint says the request was bad, sending it again will not help.

**Your handler must be idempotent.** A retry after your endpoint processed a delivery but before its response reached us is indistinguishable, from our side, from one that never arrived. Deduplicate on the event `id`.

Return `2xx` quickly and do the work afterwards. A handler that runs for thirty seconds before responding will be retried while it is still working.

An endpoint that keeps failing is eventually disabled, and shows as disabled in `agentverse webhooks list`.

## Expected result

Deliveries arriving at your endpoint within seconds of the event, each verifiable against your secret.

## Troubleshooting

**Every signature fails.** Almost certainly re-serialization — see above. Try the raw body.

**Signatures fail only sometimes.** Clock drift. Verification allows five minutes either way; a server further out than that will fail intermittently.

**Duplicate events.** Expected under retry. Deduplicate on the event `id`.

**The endpoint went quiet.** Check whether it was auto-disabled after repeated failures.

## Related guides

- [API keys and the SDKs](/docs/platform/api-keys-and-sdks)
- [Run an agent from your own code](/docs/orchestration/running-agents)
