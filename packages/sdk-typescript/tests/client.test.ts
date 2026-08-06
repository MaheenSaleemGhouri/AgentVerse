/**
 * The client and its retry policy.
 *
 * `fetch` is injected rather than mocked globally: what is being checked
 * is the request the SDK *sends* and how it treats what comes back, and
 * a real server would obscure both.
 *
 * The retry table is deliberately the same one `packages/sdk-python`
 * pins. The two SDKs share no code, and a client that retried differently
 * in one language would produce duplicate runs for half the customers —
 * the worst kind of bug to reproduce.
 */

import { describe, expect, it, vi } from "vitest";

import {
  AgentVerse,
  APIConnectionError,
  AuthenticationError,
  ConfigurationError,
  Conflict,
  NotFound,
  PermissionDenied,
  RateLimited,
  ServerError,
  ServiceUnavailable,
  ValidationError,
} from "../src/index.js";
import { RETRYABLE_STATUSES, SAFE_METHODS, decide, parseRetryAfter } from "../src/retry.js";

const BASE = "https://api.test.local";
const WORKSPACE = "ws-1";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function client(fetchImpl: typeof globalThis.fetch, maxRetries = 0): AgentVerse {
  return new AgentVerse({
    apiKey: "key-1",
    workspaceId: WORKSPACE,
    baseUrl: BASE,
    maxRetries,
    fetch: fetchImpl,
  });
}

describe("configuration", () => {
  it("refuses to construct without an API key", () => {
    // A deployment mistake should surface at startup, not on the first
    // request at 3am.
    expect(() => new AgentVerse({ workspaceId: WORKSPACE, apiKey: "" })).toThrow(
      ConfigurationError,
    );
  });

  it("refuses to construct without a workspace", () => {
    expect(() => new AgentVerse({ apiKey: "k", workspaceId: "" })).toThrow(ConfigurationError);
  });

  it("refuses a relative base URL", () => {
    expect(
      () => new AgentVerse({ apiKey: "k", workspaceId: "w", baseUrl: "api.example.com" }),
    ).toThrow(/absolute/);
  });
});

describe("request shape", () => {
  it("sends the API key as a bearer token", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(200, [])));
    await client(fetchImpl).agents.list();
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer key-1");
  });

  it("takes the workspace from the client, not the call", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(200, [])));
    await client(fetchImpl).agents.list();
    expect(String(fetchImpl.mock.calls[0]?.[0])).toContain(`/workspaces/${WORKSPACE}/agents`);
  });

  it("identifies itself", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(200, [])));
    await client(fetchImpl).agents.list();
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["User-Agent"]).toMatch(
      /^agentverse-typescript\//,
    );
  });

  it("sends no body on a GET", async () => {
    // Not `body: undefined` — `exactOptionalPropertyTypes` treats the two
    // as different requests, and some runtimes do too.
    const fetchImpl = vi.fn(() => Promise.resolve(json(200, [])));
    await client(fetchImpl).agents.list();
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect("body" in init).toBe(false);
  });
});

describe("idempotency", () => {
  it("attaches a key to every run submission", async () => {
    // A run costs money, so the safe behaviour is the default rather
    // than something to remember.
    const fetchImpl = vi.fn(() => Promise.resolve(json(202, { id: "r1" })));
    await client(fetchImpl).runs.create({ agentId: "a1", input: "hello" });
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
  });

  it("uses a supplied key verbatim", async () => {
    // A queue redelivering a job should reuse the job's id, so two
    // workers cannot start the same run twice.
    const fetchImpl = vi.fn(() => Promise.resolve(json(202, { id: "r1" })));
    await client(fetchImpl).runs.create({ agentId: "a1", input: "x", idempotencyKey: "job-42" });
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("job-42");
  });

  it("generates a different key per run", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(202, { id: "r1" })));
    const av = client(fetchImpl);
    await av.runs.create({ agentId: "a1", input: "one" });
    await av.runs.create({ agentId: "a1", input: "two" });
    const keys = fetchImpl.mock.calls.map(
      (call) => ((call[1] as RequestInit).headers as Record<string, string>)["Idempotency-Key"],
    );
    expect(new Set(keys).size).toBe(2);
  });

  it("attaches no key to a read", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(200, [])));
    await client(fetchImpl).agents.list();
    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBeUndefined();
  });
});

describe("error mapping", () => {
  it.each([
    [401, AuthenticationError],
    [403, PermissionDenied],
    [404, NotFound],
    [409, Conflict],
    [422, ValidationError],
    [429, RateLimited],
    [503, ServiceUnavailable],
    [500, ServerError],
  ])("maps %i to its own class", async (status, expected) => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(status, { detail: "nope" })));
    await expect(client(fetchImpl).agents.list()).rejects.toBeInstanceOf(expected);
  });

  it("carries retry-after on a rate limit", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(json(429, { detail: { code: "rate_limited" } }, { "Retry-After": "42" })),
    );
    await expect(client(fetchImpl).agents.list()).rejects.toMatchObject({ retryAfter: 42 });
  });

  it("does not report a 503 as a rate limit", async () => {
    // The API answers 503 when it could not check your budget, which
    // means you are not over it.
    const fetchImpl = vi.fn(() => Promise.resolve(json(503, { detail: "limiter down" })));
    await expect(client(fetchImpl).agents.list()).rejects.not.toBeInstanceOf(RateLimited);
  });

  it("attaches the request id", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(json(500, { detail: "boom" }, { "x-request-id": "req-abc" })),
    );
    await expect(client(fetchImpl).agents.list()).rejects.toMatchObject({ requestId: "req-abc" });
  });

  it("keeps the API's error code", async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(json(422, { detail: { code: "listing_not_installable", problems: ["no model"] } })),
    );
    await expect(client(fetchImpl).marketplace.install("x")).rejects.toMatchObject({
      code: "listing_not_installable",
    });
  });

  it("still errors on a non-JSON body", async () => {
    // A 502 from a proxy is still an error the caller needs to see.
    const fetchImpl = vi.fn(() =>
      Promise.resolve(new Response("<html>Bad Gateway</html>", { status: 502 })),
    );
    await expect(client(fetchImpl).agents.list()).rejects.toThrow(/Bad Gateway/);
  });

  it("reports a connection failure separately", async () => {
    // No status code and no request id; making it an APIError would give
    // callers a status of 0 to branch on.
    const fetchImpl = vi.fn(() => Promise.reject(new TypeError("fetch failed")));
    await expect(client(fetchImpl).agents.list()).rejects.toBeInstanceOf(APIConnectionError);
  });

  it("keeps instanceof working through the subclass chain", async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(json(404, { detail: "nope" })));
    await expect(client(fetchImpl).agents.list()).rejects.toSatisfy(
      (error: unknown) => error instanceof NotFound && error instanceof Error,
    );
  });
});

describe("responses", () => {
  it("does not throw on a 204", async () => {
    // Parsing an empty body would turn every successful delete into an
    // error.
    const fetchImpl = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    await expect(client(fetchImpl).agents.delete("a1")).resolves.toBeUndefined();
  });
});

describe("retry behaviour", () => {
  it("retries a read and succeeds", async () => {
    const fetchImpl = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(json(500, { detail: "boom" }))
      .mockResolvedValueOnce(json(200, [{ id: "a1" }]));
    const agents = await client(fetchImpl, 2).agents.list();
    expect(agents).toHaveLength(1);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("retries a keyed run submission", async () => {
    const fetchImpl = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(json(500, { detail: "boom" }))
      .mockResolvedValueOnce(json(202, { id: "r1" }));
    await client(fetchImpl, 2).runs.create({ agentId: "a1", input: "x" });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("does not retry an unkeyed mutation on a 500", async () => {
    // `webhooks.create` sends no key, so a 500 must not be replayed — it
    // could have created the endpoint already.
    const fetchImpl = vi.fn(() => Promise.resolve(json(500, { detail: "boom" })));
    await expect(
      client(fetchImpl, 3).webhooks.create({ url: "https://x.test/h", events: ["run.completed"] }),
    ).rejects.toBeInstanceOf(ServerError);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe("retry policy", () => {
  const fixed = (): number => 0.5;

  it.each([...RETRYABLE_STATUSES])("retries a read on %i", (status) => {
    expect(decide({ method: "GET", attempt: 0, maxRetries: 2, statusCode: status }).retry).toBe(
      true,
    );
  });

  it("does not retry a read on a client error", () => {
    expect(decide({ method: "GET", attempt: 0, maxRetries: 2, statusCode: 404 }).retry).toBe(false);
  });

  it("refuses to replay an unkeyed mutation after a connection failure", () => {
    // "No response" does not prove "never arrived": a reply lost on the
    // way back looks identical from here.
    const decision = decide({
      method: "POST",
      attempt: 0,
      maxRetries: 2,
      connectionFailed: true,
    });
    expect(decision.retry).toBe(false);
    expect(decision.reason).toContain("duplicate");
  });

  it("replays a keyed mutation after a connection failure", () => {
    expect(
      decide({
        method: "POST",
        attempt: 0,
        maxRetries: 2,
        connectionFailed: true,
        hasIdempotencyKey: true,
      }).retry,
    ).toBe(true);
  });

  it("retries an unkeyed mutation on 429 and 503 only", () => {
    // Both were refused before anything happened; a 500 does not say so.
    for (const status of [429, 503]) {
      expect(decide({ method: "POST", attempt: 0, maxRetries: 2, statusCode: status }).retry).toBe(
        true,
      );
    }
    expect(decide({ method: "POST", attempt: 0, maxRetries: 2, statusCode: 500 }).retry).toBe(
      false,
    );
  });

  it("stops at the retry budget", () => {
    expect(decide({ method: "GET", attempt: 2, maxRetries: 2, statusCode: 500 }).retry).toBe(false);
  });

  it("lets the server's Retry-After win", () => {
    expect(
      decide({ method: "GET", attempt: 0, maxRetries: 2, statusCode: 429, retryAfter: 7.5 })
        .delaySeconds,
    ).toBe(7.5);
  });

  it("caps the backoff", () => {
    expect(
      decide({ method: "GET", attempt: 20, maxRetries: 99, statusCode: 500, random: () => 1 })
        .delaySeconds,
    ).toBeLessThanOrEqual(30);
  });

  it("grows the backoff with attempts", () => {
    const delays = [0, 1, 2, 3].map(
      (attempt) =>
        decide({ method: "GET", attempt, maxRetries: 99, statusCode: 500, random: () => 1 })
          .delaySeconds,
    );
    expect(delays).toEqual([...delays].sort((a, b) => a - b));
  });

  it("uses full jitter, not a narrow band", () => {
    // When a server recovers, every client that failed during the outage
    // retries at once; randomising the whole interval spreads them.
    const low = decide({
      method: "GET",
      attempt: 3,
      maxRetries: 99,
      statusCode: 500,
      random: () => 0,
    }).delaySeconds;
    const high = decide({
      method: "GET",
      attempt: 3,
      maxRetries: 99,
      statusCode: 500,
      random: () => 1,
    }).delaySeconds;
    expect(low).toBe(0);
    expect(high).toBeGreaterThan(2);
  });

  it("clamps a negative Retry-After", () => {
    expect(
      decide({
        method: "GET",
        attempt: 0,
        maxRetries: 2,
        statusCode: 429,
        retryAfter: -5,
        random: fixed,
      }).delaySeconds,
    ).toBe(0);
  });

  it("knows which methods are safe", () => {
    expect([...SAFE_METHODS].sort()).toEqual(["GET", "HEAD", "OPTIONS"]);
  });
});

describe("Retry-After parsing", () => {
  it("reads seconds", () => {
    expect(parseRetryAfter("12")).toBe(12);
    expect(parseRetryAfter(" 3.5 ")).toBe(3.5);
  });

  it("ignores a missing header", () => {
    expect(parseRetryAfter(null)).toBeUndefined();
  });

  it("ignores an HTTP-date rather than guessing", () => {
    // Parsing dates would mean trusting the client's clock to agree with
    // the server's; falling back to our own backoff is safer.
    expect(parseRetryAfter("Wed, 21 Oct 2026 07:28:00 GMT")).toBeUndefined();
  });

  it("ignores a negative value", () => {
    expect(parseRetryAfter("-1")).toBeUndefined();
  });
});
