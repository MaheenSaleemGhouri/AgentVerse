/**
 * Typed errors, so callers branch on a class rather than a status code.
 *
 * The distinctions that earn their place:
 *
 * - `RateLimited` carries `retryAfter`, so a caller backs off correctly
 *   without parsing a header.
 * - `ServiceUnavailable` is deliberately *not* `RateLimited`. The API
 *   answers 503 when it could not check your budget — you are not over
 *   it — and a client that logged that as a rate limit would chase the
 *   wrong problem.
 * - `NotFound` is what a cross-workspace resource returns. The API
 *   answers 404 rather than 403 so a workspace's existence is not
 *   discoverable, and the SDK does not undo that by guessing.
 */

export class AgentVerseError extends Error {
  constructor(message: string) {
    super(message);
    // Without this, `instanceof` fails for subclasses when the package is
    // compiled down to ES5 by a consumer's bundler — and a caller's
    // `catch (e) { if (e instanceof NotFound) }` silently stops working.
    this.name = new.target.name;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ConfigurationError extends AgentVerseError {}

export interface APIErrorOptions {
  statusCode: number;
  code?: string | undefined;
  requestId?: string | undefined;
  details?: unknown;
}

export class APIError extends AgentVerseError {
  readonly statusCode: number;
  readonly code: string | undefined;
  /**
   * Echoed from the response. Quoting it in a support conversation finds
   * the exact request in our logs, which is the entire reason the header
   * exists — an SDK that drops it forces the customer to describe their
   * problem in prose.
   */
  readonly requestId: string | undefined;
  readonly details: unknown;

  constructor(message: string, options: APIErrorOptions) {
    const suffix = options.requestId ? `, request ${options.requestId}` : "";
    super(`${message} (HTTP ${String(options.statusCode)}${suffix})`);
    this.statusCode = options.statusCode;
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
  }
}

export class AuthenticationError extends APIError {}
export class PermissionDenied extends APIError {}
export class NotFound extends APIError {}
export class Conflict extends APIError {}
export class ValidationError extends APIError {}
export class ServiceUnavailable extends APIError {}
export class ServerError extends APIError {}

export class RateLimited extends APIError {
  /** Seconds to wait, from the server. `undefined` only if absent. */
  readonly retryAfter: number | undefined;

  constructor(message: string, options: APIErrorOptions & { retryAfter?: number | undefined }) {
    super(message, options);
    this.retryAfter = options.retryAfter;
  }
}

/**
 * The request never got an answer: DNS, TLS, timeout, abort.
 *
 * Not an `APIError`, because there is no status code and no request id —
 * making it one would give callers a status of 0 to branch on.
 */
export class APIConnectionError extends AgentVerseError {}

export function errorForStatus(
  message: string,
  options: APIErrorOptions & { retryAfter?: number | undefined },
): APIError {
  switch (options.statusCode) {
    case 401:
      return new AuthenticationError(message, options);
    case 403:
      return new PermissionDenied(message, options);
    case 404:
      return new NotFound(message, options);
    case 409:
      return new Conflict(message, options);
    case 422:
      return new ValidationError(message, options);
    case 429:
      return new RateLimited(message, options);
    case 503:
      return new ServiceUnavailable(message, options);
    default:
      return options.statusCode >= 500
        ? new ServerError(message, options)
        : new APIError(message, options);
  }
}
