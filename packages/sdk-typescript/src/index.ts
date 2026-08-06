/**
 * Official TypeScript SDK for the AgentVerse API.
 *
 * ```ts
 * import { AgentVerse } from "@agentverse/sdk";
 *
 * const av = new AgentVerse();            // AGENTVERSE_API_KEY, AGENTVERSE_WORKSPACE_ID
 * const install = await av.marketplace.install("research-assistant");
 * const run = await av.runs.create({ agentId: install.agent_id, input: "Summarise this." });
 * ```
 *
 * Verifying an inbound webhook does not need a client or a key:
 * `import { verifyWebhook } from "@agentverse/sdk/webhooks"`.
 */

export { AgentVerse, DEFAULT_BASE_URL } from "./client.js";
export type {
  Agent,
  AgentVerseOptions,
  CreatedWebhookEndpoint,
  InstallResult,
  InstalledListing,
  Listing,
  ListingPage,
  Run,
  WebhookDelivery,
  WebhookEndpoint,
} from "./client.js";
export {
  AgentVerseError,
  APIConnectionError,
  APIError,
  AuthenticationError,
  ConfigurationError,
  Conflict,
  NotFound,
  PermissionDenied,
  RateLimited,
  ServerError,
  ServiceUnavailable,
  ValidationError,
} from "./errors.js";
export {
  DEFAULT_TOLERANCE_SECONDS,
  SIGNATURE_HEADER,
  SignatureVerificationError,
  computeSignature,
  verifyWebhook,
} from "./webhooks.js";
export type { WebhookEvent } from "./webhooks.js";
