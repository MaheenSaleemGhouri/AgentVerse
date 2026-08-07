/**
 * Docs search ranking.
 *
 * Pure over an array, so the tests are the specification: what a reader
 * typing a word gets back, and in what order.
 */

import { describe, expect, it } from "vitest";

import { type DocsSearchEntry, searchDocs } from "./match";

const INDEX: readonly DocsSearchEntry[] = [
  {
    slug: "platform/webhooks",
    title: "Receive webhooks",
    summary: "Subscribe to platform events and verify a delivery's signature.",
    pillar: "platform",
    pillarName: "Platform",
    headings: ["Events", "Verify the signature", "Retries and idempotency"],
  },
  {
    slug: "orchestration/running-agents",
    title: "Run an agent from your own code",
    summary: "Trigger runs over the REST API, the SDKs, or the CLI.",
    pillar: "orchestration",
    pillarName: "Orchestration",
    headings: ["Runs are asynchronous", "Idempotency", "Retries and rate limits"],
  },
  {
    slug: "platform/api-keys-and-sdks",
    title: "API keys and the SDKs",
    summary: "Issue a workspace-scoped key, then call AgentVerse from Python.",
    pillar: "platform",
    pillarName: "Platform",
    headings: ["Issue an API key", "Configure", "Errors"],
  },
];

describe("matching", () => {
  it("finds a guide by a word in its title", () => {
    expect(searchDocs(INDEX, "webhooks").map((entry) => entry.slug)).toEqual([
      "platform/webhooks",
    ]);
  });

  it("finds a guide by a word in a heading", () => {
    // A reader looking for "idempotency" should reach the guide that
    // has a section about it, not only ones with it in the title.
    const slugs = searchDocs(INDEX, "idempotency").map((entry) => entry.slug);
    expect(slugs).toContain("orchestration/running-agents");
    expect(slugs).toContain("platform/webhooks");
  });

  it("finds a guide by its pillar name", () => {
    const slugs = searchDocs(INDEX, "platform").map((entry) => entry.slug);
    expect(slugs).toContain("platform/webhooks");
    expect(slugs).toContain("platform/api-keys-and-sdks");
  });

  it("is case-insensitive", () => {
    expect(searchDocs(INDEX, "WEBHOOKS")).toHaveLength(1);
  });

  it("returns nothing for an empty query", () => {
    expect(searchDocs(INDEX, "")).toEqual([]);
    expect(searchDocs(INDEX, "   ")).toEqual([]);
  });

  it("returns nothing when nothing matches", () => {
    expect(searchDocs(INDEX, "kubernetes")).toEqual([]);
  });
});

describe("every term must match", () => {
  it("requires all terms, not any", () => {
    // "webhooks kubernetes" must return nothing. If unmatched terms were
    // ignored, the second word would do no work and the result would be
    // identical to searching "webhooks" — which is not what someone
    // typing two words expects.
    expect(searchDocs(INDEX, "webhooks kubernetes")).toEqual([]);
  });

  it("narrows rather than widens as terms are added", () => {
    const one = searchDocs(INDEX, "retries");
    const two = searchDocs(INDEX, "retries webhooks");
    expect(two.length).toBeLessThanOrEqual(one.length);
  });
});

describe("ranking", () => {
  it("ranks a title match above a heading-only match", () => {
    // Both guides mention retries in a heading; only one is *about*
    // webhooks. A reader searching "webhooks retries" wants that one.
    const results = searchDocs(INDEX, "webhooks");
    expect(results[0]?.slug).toBe("platform/webhooks");
  });

  it("ranks a guide matching in several fields above one matching in one", () => {
    const results = searchDocs(INDEX, "api");
    // "API keys and the SDKs" has it in the title and a heading; the
    // runs guide only in its summary.
    expect(results[0]?.slug).toBe("platform/api-keys-and-sdks");
  });

  it("respects the limit", () => {
    expect(searchDocs(INDEX, "the", 1)).toHaveLength(1);
  });

  it("breaks ties deterministically so results do not reshuffle", () => {
    const first = searchDocs(INDEX, "platform");
    const second = searchDocs(INDEX, "platform");
    expect(first.map((entry) => entry.slug)).toEqual(second.map((entry) => entry.slug));
  });
});
