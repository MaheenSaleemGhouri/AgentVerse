# @agentverse/sdk

Official TypeScript client for the AgentVerse API.

```bash
npm install @agentverse/sdk
```

```ts
import { AgentVerse } from "@agentverse/sdk";

const av = new AgentVerse();               // AGENTVERSE_API_KEY, AGENTVERSE_WORKSPACE_ID
const install = await av.marketplace.install("research-assistant");
const run = await av.runs.create({ agentId: install.agent_id, input: "Summarise this." });
```

Response types come from `@agentverse/contracts`, generated from the
API's own OpenAPI schema — a shape that changes server-side breaks this
package's build rather than your runtime.

## Verifying webhooks

```ts
import { verifyWebhook, SignatureVerificationError } from "@agentverse/sdk/webhooks";

app.post("/webhooks/agentverse", express.raw({ type: "application/json" }), (req, res) => {
  try {
    const event = verifyWebhook({
      payload: req.body,                          // raw bytes, not express.json()
      signatureHeader: req.header("AgentVerse-Signature") ?? "",
      secret: process.env.AGENTVERSE_WEBHOOK_SECRET!,
    });
  } catch (error) {
    if (error instanceof SignatureVerificationError) return res.sendStatus(400);
    throw error;
  }
});
```

`express.json()` instead of `express.raw()` is the most common way to
break this: the signature is over bytes, and a re-serialized object is
not the same bytes.

## Retries

Reads retry on 408/429/5xx with exponential backoff and full jitter; a
server's `Retry-After` always wins. Mutations retry **only** when they
carry an `Idempotency-Key` — `runs.create()` generates one, because a run
costs money.

## Status

Built and tested in this repository; **not yet published to npm**.
