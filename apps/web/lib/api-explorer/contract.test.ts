/**
 * Every endpoint the explorer offers must actually exist.
 *
 * This catches the one failure mode a hand-curated catalogue has: a path
 * typed from memory that the API never served, or one that was renamed
 * out from under it. Both look identical to a user — a 404 from a
 * control the product itself put in front of them — and neither is
 * visible in review.
 *
 * `apps/api/openapi.json` is the checked-in export the SDK types are
 * generated from, so it is the same source of truth the rest of the
 * monorepo trusts. Two of these entries were wrong when this test was
 * first written; that is what it is for.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { EXPLORER_ENDPOINTS } from "./endpoints";

interface OpenApiDocument {
  paths: Record<string, Record<string, unknown>>;
}

const schema = JSON.parse(
  readFileSync(path.join(process.cwd(), "..", "..", "apps", "api", "openapi.json"), "utf8"),
) as OpenApiDocument;

describe("explorer endpoints against the OpenAPI contract", () => {
  it("the schema loaded and has paths", () => {
    // Guards the guard: a broken path to `openapi.json` would make every
    // assertion below vacuously pass.
    expect(Object.keys(schema.paths).length).toBeGreaterThan(20);
  });

  it.each(EXPLORER_ENDPOINTS.map((endpoint) => [endpoint.id, endpoint] as const))(
    "%s exists and serves GET",
    (_id, endpoint) => {
      const operations = schema.paths[endpoint.path];
      expect(
        operations,
        `${endpoint.path} is not in openapi.json — the explorer would 404`,
      ).toBeDefined();
      expect(operations).toHaveProperty("get");
    },
  );

  it.each(EXPLORER_ENDPOINTS.map((endpoint) => [endpoint.id, endpoint] as const))(
    "%s declares every path parameter the URL contains",
    (_id, endpoint) => {
      const placeholders = [...endpoint.path.matchAll(/\{(\w+)\}/g)].map((match) => match[1]);
      // `workspace_id` is supplied by the app, the rest by the form.
      const supplied = ["workspace_id", ...(endpoint.pathParams ?? []).map((p) => p.name)];
      for (const placeholder of placeholders) {
        expect(supplied).toContain(placeholder);
      }
    },
  );
});
