/**
 * When to retry, and how long to wait. Pure — no clock, no network.
 *
 * Separated from the client so the policy is testable without sleeping
 * and without a server, which is the only way to check what matters:
 * that the server's `Retry-After` wins over the client's guess, and that
 * a non-idempotent request is never silently replayed.
 *
 * **The rule that carries money.** Retrying a `POST` that already reached
 * the server is how one agent run becomes two, and one charge becomes
 * two. So: retry a mutation only when the caller supplied an
 * `Idempotency-Key`, or when the status says the request was refused
 * before anything happened. Reads retry freely.
 *
 * Deliberately mirrors `packages/sdk-python`'s policy. The two SDKs are
 * separate packages with no shared code, and the tests on both sides pin
 * the same table — a client that retried differently in one language
 * would produce duplicate runs only for half the customers, which is the
 * worst kind of bug to reproduce.
 */

export const RETRYABLE_STATUSES: ReadonlySet<number> = new Set([408, 429, 500, 502, 503, 504]);
export const SAFE_METHODS: ReadonlySet<string> = new Set(["GET", "HEAD", "OPTIONS"]);

export const DEFAULT_MAX_RETRIES = 2;
const BASE_DELAY_SECONDS = 0.5;
const MAX_DELAY_SECONDS = 30;

export interface RetryDecision {
  retry: boolean;
  delaySeconds: number;
  reason: string;
}

export interface RetryInput {
  method: string;
  /** 0-based: how many retries have already been made. */
  attempt: number;
  maxRetries: number;
  statusCode?: number | undefined;
  retryAfter?: number | undefined;
  hasIdempotencyKey?: boolean;
  connectionFailed?: boolean;
  /** Injectable so the tests are not flaky. Returns [0, 1). */
  random?: () => number;
}

function backoff(attempt: number, random: () => number): number {
  // Full jitter, not a band around a base: when a server recovers, every
  // client that failed during the outage retries at once, and that herd
  // is what keeps it down. Randomising the whole interval spreads them.
  const ceiling = Math.min(BASE_DELAY_SECONDS * 2 ** attempt, MAX_DELAY_SECONDS);
  return random() * ceiling;
}

export function decide(input: RetryInput): RetryDecision {
  const random = input.random ?? Math.random;
  if (input.attempt >= input.maxRetries) {
    return { retry: false, delaySeconds: 0, reason: "retry budget exhausted" };
  }

  const isSafe = SAFE_METHODS.has(input.method.toUpperCase());
  const hasKey = input.hasIdempotencyKey ?? false;

  if (input.connectionFailed === true) {
    // "No response" does not prove "never arrived": a reply lost on the
    // way back looks identical from here.
    if (isSafe || hasKey) {
      return { retry: true, delaySeconds: backoff(input.attempt, random), reason: "connection failed" };
    }
    return {
      retry: false,
      delaySeconds: 0,
      reason: "connection failed on a mutation with no Idempotency-Key — retrying could duplicate it",
    };
  }

  const status = input.statusCode;
  if (status === undefined || !RETRYABLE_STATUSES.has(status)) {
    return { retry: false, delaySeconds: 0, reason: "not a retryable status" };
  }

  // A 429 or 503 was refused before anything happened, so retrying is
  // safe even unkeyed. A 500 or 502 does not say that, and the SDK does
  // not get to guess which one this deployment meant.
  if (!isSafe && !hasKey && status !== 429 && status !== 503) {
    return {
      retry: false,
      delaySeconds: 0,
      reason: "server error on a mutation with no Idempotency-Key — retrying could duplicate it",
    };
  }

  if (input.retryAfter !== undefined) {
    // The server's number always wins: it knows when the window reopens,
    // and a client that guesses shorter simply gets refused again.
    return {
      retry: true,
      delaySeconds: Math.max(input.retryAfter, 0),
      reason: "server asked us to wait",
    };
  }

  return {
    retry: true,
    delaySeconds: backoff(input.attempt, random),
    reason: `retryable status ${String(status)}`,
  };
}

/**
 * `Retry-After` as seconds, or `undefined` if unusable.
 *
 * Only delta-seconds. The HTTP-date form is legal but this API never
 * sends it, and parsing dates would mean trusting the client's clock to
 * agree with the server's; falling back to our own backoff is safer.
 */
export function parseRetryAfter(value: string | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  const seconds = Number.parseFloat(value.trim());
  if (Number.isNaN(seconds) || seconds < 0) return undefined;
  return seconds;
}
