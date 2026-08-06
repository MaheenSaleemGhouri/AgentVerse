/**
 * Verifying an inbound AgentVerse webhook.
 *
 * The highest-value thing in the SDK, because it is the piece every
 * customer would otherwise write themselves and every mistake is silent:
 *
 * - comparing signatures with `===`, which leaks the expected value one
 *   byte at a time to anyone who can measure the response time;
 * - ignoring the timestamp, which makes a captured delivery replayable
 *   forever;
 * - verifying `JSON.stringify(req.body)` rather than the raw bytes,
 *   which breaks the moment the receiver's JSON differs by one space —
 *   and breaks in a way that looks like *our* signatures being wrong.
 *
 * The signature is over bytes, so `payload` is bytes. Express users:
 * `express.raw({ type: "application/json" })`, not `express.json()`.
 *
 * ```ts
 * import { verifyWebhook, SignatureVerificationError } from "@agentverse/sdk/webhooks";
 *
 * app.post("/webhooks/agentverse", express.raw({ type: "application/json" }), (req, res) => {
 *   try {
 *     const event = verifyWebhook({
 *       payload: req.body,
 *       signatureHeader: req.header("AgentVerse-Signature") ?? "",
 *       secret: process.env.AGENTVERSE_WEBHOOK_SECRET!,
 *     });
 *   } catch (error) {
 *     if (error instanceof SignatureVerificationError) return res.sendStatus(400);
 *     throw error;
 *   }
 * });
 * ```
 */

import { createHmac, timingSafeEqual } from "node:crypto";

export const SIGNATURE_HEADER = "AgentVerse-Signature";
export const SIGNATURE_VERSION = "v1";

/**
 * How far out of date a delivery may be. Generous enough for a receiver
 * behind a slow queue, short enough that a captured delivery stops being
 * useful quickly.
 */
export const DEFAULT_TOLERANCE_SECONDS = 300;

/**
 * One error for a bad signature *and* a stale timestamp, deliberately: a
 * receiver that answered differently would tell an attacker which half
 * of their forgery to fix.
 */
export class SignatureVerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SignatureVerificationError";
    Object.setPrototypeOf(this, SignatureVerificationError.prototype);
  }
}

export interface WebhookEvent {
  id: string;
  type: string;
  api_version: string;
  created_at: string;
  data: Record<string, unknown>;
}

export function computeSignature(options: {
  payload: Uint8Array | string;
  secret: string;
  timestamp: number;
}): string {
  const raw =
    typeof options.payload === "string"
      ? Buffer.from(options.payload, "utf8")
      : Buffer.from(options.payload);
  const signed = Buffer.concat([Buffer.from(`${String(options.timestamp)}.`, "utf8"), raw]);
  return createHmac("sha256", options.secret).update(signed).digest("hex");
}

function parseHeader(header: string): { timestamp: number; signatures: string[] } {
  let timestamp: number | undefined;
  const signatures: string[] = [];
  for (const part of header.split(",")) {
    const [key, ...rest] = part.trim().split("=");
    const value = rest.join("=");
    if (key === "t") {
      const parsed = Number.parseInt(value, 10);
      if (Number.isNaN(parsed)) {
        throw new SignatureVerificationError("Malformed timestamp in signature header");
      }
      timestamp = parsed;
    } else if (key === SIGNATURE_VERSION) {
      // Every `v1=` value, not just the first: the format allows several
      // so a secret rotation can be signed under both, and a parser that
      // read only the first would reject half the deliveries during
      // exactly the window rotation exists to make safe.
      signatures.push(value);
    }
  }
  if (timestamp === undefined || signatures.length === 0) {
    throw new SignatureVerificationError("Signature header is missing a timestamp or a digest");
  }
  return { timestamp, signatures };
}

function constantTimeEquals(a: string, b: string): boolean {
  // `timingSafeEqual` throws on unequal lengths, which would itself leak
  // the expected length — so the lengths are compared first and the
  // result short-circuits without touching the bytes.
  if (a.length !== b.length) return false;
  return timingSafeEqual(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
}

export function verifyWebhook(options: {
  /** The **raw** body. Not a parsed object, not a re-serialized one. */
  payload: Uint8Array | string;
  signatureHeader: string;
  secret: string;
  toleranceSeconds?: number;
  /** Unix seconds. Injectable so tests do not depend on the wall clock. */
  now?: number;
}): WebhookEvent {
  const tolerance = options.toleranceSeconds ?? DEFAULT_TOLERANCE_SECONDS;
  const { timestamp, signatures } = parseHeader(options.signatureHeader);

  const current = options.now ?? Date.now() / 1000;
  if (tolerance > 0 && Math.abs(current - timestamp) > tolerance) {
    // Checked before the digest, so a stale delivery costs nothing to
    // discard. `Math.abs` covers clocks in both directions: a receiver
    // running fast would otherwise accept deliveries from its own future
    // indefinitely.
    throw new SignatureVerificationError(
      `Delivery timestamp is outside the ${String(tolerance)}s tolerance`,
    );
  }

  const expected = computeSignature({
    payload: options.payload,
    secret: options.secret,
    timestamp,
  });
  if (!signatures.some((provided) => constantTimeEquals(expected, provided))) {
    throw new SignatureVerificationError("Signature does not match");
  }

  const text =
    typeof options.payload === "string"
      ? options.payload
      : Buffer.from(options.payload).toString("utf8");

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new SignatureVerificationError("Verified payload is not valid JSON");
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw new SignatureVerificationError("Verified payload is not an object");
  }

  const record = body as Record<string, unknown>;
  const data = record["data"];
  return {
    id: typeof record["id"] === "string" ? record["id"] : "",
    type: typeof record["type"] === "string" ? record["type"] : "",
    api_version: typeof record["api_version"] === "string" ? record["api_version"] : "",
    created_at: typeof record["created_at"] === "string" ? record["created_at"] : "",
    // A receiver should not have to guard `event.data` for null on an
    // event that happens to carry no body.
    data: typeof data === "object" && data !== null ? (data as Record<string, unknown>) : {},
  };
}
