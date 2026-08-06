/**
 * The AgentVerse client.
 *
 * **Response types come from `@agentverse/contracts`, not from hand-written
 * interfaces.** Those are generated from the API's own OpenAPI schema, so
 * a shape that changes server-side breaks this package's build rather
 * than a customer's runtime. Re-declaring them here would be a third copy
 * of the same truth (Rule 3), and the copy that goes stale.
 *
 * **`workspaceId` is bound once, at construction.** Every API key is
 * issued for exactly one workspace, so threading it through each call
 * asks the caller to repeat what their credential already fixes — and to
 * get it wrong in a way the server answers with a bare 404.
 */

import type { components } from "@agentverse/contracts";

import {
  APIConnectionError,
  APIError,
  ConfigurationError,
  errorForStatus,
} from "./errors.js";
import { DEFAULT_MAX_RETRIES, decide, parseRetryAfter } from "./retry.js";

type Schemas = components["schemas"];

export type Agent = Schemas["AgentResponse"];
export type Run = Schemas["RunResponse"];
export type Listing = Schemas["ListingResponse"];
export type ListingPage = Schemas["ListingPageResponse"];
export type InstallResult = Schemas["InstallResponse"];
export type InstalledListing = Schemas["InstalledListingResponse"];
export type WebhookEndpoint = Schemas["EndpointResponse"];
export type CreatedWebhookEndpoint = Schemas["CreatedEndpointResponse"];
export type WebhookDelivery = Schemas["DeliveryResponse"];

export const DEFAULT_BASE_URL = "https://api.agentverse.dev";
const USER_AGENT = "agentverse-typescript/0.1.0-alpha";
const REQUEST_ID_HEADER = "x-request-id";

export interface AgentVerseOptions {
  apiKey?: string;
  workspaceId?: string;
  baseUrl?: string;
  maxRetries?: number;
  /** Injectable for tests and for callers with their own instrumentation. */
  fetch?: typeof globalThis.fetch;
}

interface RequestOptions {
  method: string;
  path: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  idempotencyKey?: string;
}

function sleep(seconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
}

interface ExtractedError {
  message: string;
  code?: string | undefined;
  details?: unknown;
}

function extractError(status: number, text: string): ExtractedError {
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    // A 502 from a proxy in front of the API is still an error the caller
    // needs to see; swallowing it for having the wrong shape would turn
    // it into "unknown error".
    return { message: text || `HTTP ${String(status)}` };
  }
  if (typeof body === "object" && body !== null) {
    const detail = (body as Record<string, unknown>)["detail"];
    if (typeof detail === "string") return { message: detail };
    if (Array.isArray(detail)) {
      // FastAPI's validation shape. Kept structured: a caller building a
      // form needs to know which field failed.
      return { message: "Request validation failed", code: "validation_error", details: detail };
    }
    if (typeof detail === "object" && detail !== null) {
      const record = detail as Record<string, unknown>;
      const message = record["message"] ?? record["code"] ?? "Request failed";
      return {
        message: typeof message === "string" ? message : "Request failed",
        code: typeof record["code"] === "string" ? record["code"] : undefined,
        details: detail,
      };
    }
  }
  return { message: `HTTP ${String(status)}`, details: body };
}

export class AgentVerse {
  readonly workspaceId: string;
  readonly #apiKey: string;
  readonly #baseUrl: string;
  readonly #maxRetries: number;
  readonly #fetch: typeof globalThis.fetch;

  readonly agents: Agents;
  readonly runs: Runs;
  readonly marketplace: Marketplace;
  readonly webhooks: Webhooks;

  constructor(options: AgentVerseOptions = {}) {
    const apiKey = options.apiKey ?? process.env["AGENTVERSE_API_KEY"];
    if (apiKey === undefined || apiKey === "") {
      // Thrown at construction, not on the first call: a missing key is a
      // deployment mistake and should surface at startup.
      throw new ConfigurationError("No API key. Pass apiKey or set AGENTVERSE_API_KEY.");
    }
    const workspaceId = options.workspaceId ?? process.env["AGENTVERSE_WORKSPACE_ID"];
    if (workspaceId === undefined || workspaceId === "") {
      throw new ConfigurationError(
        "No workspace. Pass workspaceId or set AGENTVERSE_WORKSPACE_ID.",
      );
    }
    const baseUrl = options.baseUrl ?? process.env["AGENTVERSE_BASE_URL"] ?? DEFAULT_BASE_URL;
    if (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://")) {
      throw new ConfigurationError(`baseUrl must be an absolute http(s) URL, got ${baseUrl}`);
    }

    this.workspaceId = workspaceId;
    this.#apiKey = apiKey;
    this.#baseUrl = baseUrl.replace(/\/+$/, "");
    this.#maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.#fetch = options.fetch ?? globalThis.fetch.bind(globalThis);

    this.agents = new Agents(this);
    this.runs = new Runs(this);
    this.marketplace = new Marketplace(this);
    this.webhooks = new Webhooks(this);
  }

  /** @internal */
  async request<T>(options: RequestOptions): Promise<T> {
    const url = new URL(this.#baseUrl + options.path);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }

    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.#apiKey}`,
      "User-Agent": USER_AGENT,
      Accept: "application/json",
    };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (options.idempotencyKey !== undefined) {
      headers["Idempotency-Key"] = options.idempotencyKey;
    }

    let attempt = 0;
    for (;;) {
      let response: Response;
      try {
        // Built conditionally rather than passing `body: undefined`:
        // `exactOptionalPropertyTypes` treats the two as different, and
        // a GET carrying an explicit undefined body is not the same
        // request as one with no body key at all.
        const init: RequestInit = { method: options.method, headers };
        if (options.body !== undefined) init.body = JSON.stringify(options.body);
        response = await this.#fetch(url, init);
      } catch (cause) {
        const decision = decide({
          method: options.method,
          attempt,
          maxRetries: this.#maxRetries,
          connectionFailed: true,
          hasIdempotencyKey: options.idempotencyKey !== undefined,
        });
        if (!decision.retry) {
          throw new APIConnectionError(cause instanceof Error ? cause.message : String(cause));
        }
        await sleep(decision.delaySeconds);
        attempt += 1;
        continue;
      }

      if (response.ok) {
        // 204 has no body by definition; calling `.json()` on it throws,
        // and letting that escape would turn every successful delete into
        // an error.
        if (response.status === 204) return undefined as T;
        const text = await response.text();
        return (text === "" ? undefined : JSON.parse(text)) as T;
      }

      const retryAfter = parseRetryAfter(response.headers.get("Retry-After"));
      const decision = decide({
        method: options.method,
        attempt,
        maxRetries: this.#maxRetries,
        statusCode: response.status,
        retryAfter,
        hasIdempotencyKey: options.idempotencyKey !== undefined,
      });
      if (!decision.retry) {
        const { message, code, details } = extractError(response.status, await response.text());
        throw errorForStatus(message, {
          statusCode: response.status,
          code,
          requestId: response.headers.get(REQUEST_ID_HEADER) ?? undefined,
          details,
          retryAfter,
        });
      }
      await sleep(decision.delaySeconds);
      attempt += 1;
    }
  }

  /** @internal */
  workspacePath(suffix: string): string {
    return `/api/v1/workspaces/${this.workspaceId}${suffix}`;
  }
}

class Agents {
  constructor(private readonly client: AgentVerse) {}

  list(): Promise<Agent[]> {
    return this.client.request<Agent[]>({
      method: "GET",
      path: this.client.workspacePath("/agents"),
    });
  }

  create(input: {
    name: string;
    model: string;
    system_instructions: string;
    description?: string;
    temperature?: number;
    max_output_tokens?: number;
    tools?: string[];
    knowledge_base_ids?: string[];
  }): Promise<Agent> {
    return this.client.request<Agent>({
      method: "POST",
      path: this.client.workspacePath("/agents"),
      body: input,
    });
  }

  get(agentId: string): Promise<Agent> {
    return this.client.request<Agent>({
      method: "GET",
      path: this.client.workspacePath(`/agents/${agentId}`),
    });
  }

  async delete(agentId: string): Promise<void> {
    // `request<undefined>` rather than `request<void>`: `void` is not a
    // legal type argument, and the API answers 204 with no body — which
    // is `undefined`, not "nothing".
    await this.client.request<undefined>({
      method: "DELETE",
      path: this.client.workspacePath(`/agents/${agentId}`),
    });
  }
}

class Runs {
  constructor(private readonly client: AgentVerse) {}

  /**
   * Submit a run. Returns immediately with a run id.
   *
   * An idempotency key is generated when none is given, because a run
   * costs money and a retried POST that already arrived is how one charge
   * becomes two. Supply your own when the *caller* can retry: a queue
   * redelivering a job should reuse the job's id, so two workers cannot
   * start the same run twice.
   */
  create(input: { agentId: string; input: string; idempotencyKey?: string }): Promise<Run> {
    return this.client.request<Run>({
      method: "POST",
      path: this.client.workspacePath(`/agents/${input.agentId}/runs`),
      body: { input: input.input },
      idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
    });
  }
}

class Marketplace {
  constructor(private readonly client: AgentVerse) {}

  listings(query: {
    category?: string;
    q?: string;
    free?: boolean;
    official?: boolean;
    sort?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<ListingPage> {
    return this.client.request<ListingPage>({
      method: "GET",
      path: "/api/v1/marketplace/listings",
      query,
    });
  }

  /** The first-party template library. */
  templates(query: { category?: string } = {}): Promise<Listing[]> {
    return this.client.request<Listing[]>({
      method: "GET",
      path: "/api/v1/marketplace/templates",
      query,
    });
  }

  get(slug: string): Promise<Listing> {
    return this.client.request<Listing>({
      method: "GET",
      path: `/api/v1/marketplace/listings/${slug}`,
    });
  }

  /**
   * Copy a published listing into this workspace as a new agent.
   *
   * Idempotent server-side per (workspace, listing, version), so a
   * repeated call returns the same agent rather than a second one.
   */
  install(slug: string, options: { versionNumber?: number; name?: string } = {}): Promise<InstallResult> {
    return this.client.request<InstallResult>({
      method: "POST",
      path: this.client.workspacePath(`/marketplace/listings/${slug}/install`),
      body: {
        ...(options.versionNumber === undefined ? {} : { version_number: options.versionNumber }),
        ...(options.name === undefined ? {} : { name: options.name }),
      },
    });
  }

  installs(): Promise<InstalledListing[]> {
    return this.client.request<InstalledListing[]>({
      method: "GET",
      path: this.client.workspacePath("/marketplace/installs"),
    });
  }
}

class Webhooks {
  constructor(private readonly client: AgentVerse) {}

  list(): Promise<WebhookEndpoint[]> {
    return this.client.request<WebhookEndpoint[]>({
      method: "GET",
      path: this.client.workspacePath("/webhooks"),
    });
  }

  /**
   * Register an endpoint. The signing secret is in the response, once —
   * store it now, it is not readable later.
   */
  create(input: { url: string; events: string[]; description?: string }): Promise<CreatedWebhookEndpoint> {
    return this.client.request<CreatedWebhookEndpoint>({
      method: "POST",
      path: this.client.workspacePath("/webhooks"),
      body: { url: input.url, events: input.events, description: input.description ?? "" },
    });
  }

  eventTypes(): Promise<string[]> {
    return this.client.request<string[]>({
      method: "GET",
      path: this.client.workspacePath("/webhooks/events"),
    });
  }

  deliveries(query: { endpointId?: string; limit?: number } = {}): Promise<WebhookDelivery[]> {
    return this.client.request<WebhookDelivery[]>({
      method: "GET",
      path: this.client.workspacePath("/webhooks/deliveries"),
      query: { endpoint_id: query.endpointId, limit: query.limit },
    });
  }

  async delete(endpointId: string): Promise<void> {
    await this.client.request<undefined>({
      method: "DELETE",
      path: this.client.workspacePath(`/webhooks/${endpointId}`),
    });
  }
}

export { APIError };
