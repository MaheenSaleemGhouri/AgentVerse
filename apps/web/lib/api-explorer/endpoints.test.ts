/**
 * Path building for the API explorer.
 *
 * Pure, and worth pinning: the server action rebuilds the path from
 * these functions rather than trusting one from the client, so a bug
 * here is a bug in what the explorer is allowed to call.
 */

import { describe, expect, it } from "vitest";

import {
  EXPLORER_ENDPOINTS,
  type ExplorerEndpoint,
  buildPath,
  isComplete,
} from "./endpoints";

const WORKSPACE = "ws-1";

function endpoint(id: string): ExplorerEndpoint {
  const found = EXPLORER_ENDPOINTS.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`No such endpoint: ${id}`);
  return found;
}

describe("the catalogue itself", () => {
  it("offers only read-only endpoints", () => {
    // The guarantee the explorer's UI copy makes to the user. A POST
    // slipping into this list would let a curious click trigger a
    // billable run.
    for (const candidate of EXPLORER_ENDPOINTS) {
      expect(candidate.method).toBe("GET");
    }
  });

  it("has unique ids, since the server action looks endpoints up by id", () => {
    const ids = EXPLORER_ENDPOINTS.map((candidate) => candidate.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("declares a path param for every placeholder other than workspace_id", () => {
    for (const candidate of EXPLORER_ENDPOINTS) {
      const placeholders = [...candidate.path.matchAll(/\{(\w+)\}/g)]
        .map((match) => match[1])
        .filter((name) => name !== "workspace_id");
      const declared = (candidate.pathParams ?? []).map((param) => param.name);
      // An undeclared placeholder would survive into the request URL as
      // a literal `{agent_id}` and 404 with no way for the user to see
      // why.
      expect(placeholders.sort()).toEqual(declared.sort());
    }
  });
});

describe("buildPath", () => {
  it("substitutes the active workspace", () => {
    expect(buildPath(endpoint("list-agents"), WORKSPACE, {}, {})).toBe(
      "/api/v1/workspaces/ws-1/agents",
    );
  });

  it("substitutes a path parameter", () => {
    expect(buildPath(endpoint("get-agent"), WORKSPACE, { agent_id: "a1" }, {})).toBe(
      "/api/v1/workspaces/ws-1/agents/a1",
    );
  });

  it("url-encodes path parameters", () => {
    // A slash in a path value would otherwise invent a path segment.
    expect(
      buildPath(endpoint("get-listing"), WORKSPACE, { slug: "a/b?c=d" }, {}),
    ).toBe("/api/v1/marketplace/listings/a%2Fb%3Fc%3Dd");
  });

  it("appends only the query parameters that have values", () => {
    expect(
      buildPath(endpoint("list-listings"), WORKSPACE, {}, { q: "research", category: "" }),
    ).toBe("/api/v1/marketplace/listings?q=research");
  });

  it("omits the question mark entirely when nothing is set", () => {
    expect(buildPath(endpoint("list-listings"), WORKSPACE, {}, {})).toBe(
      "/api/v1/marketplace/listings",
    );
  });

  it("encodes query values", () => {
    expect(buildPath(endpoint("search"), WORKSPACE, {}, { q: "a b&c" })).toContain(
      "q=a+b%26c",
    );
  });

  it("ignores a value for a parameter the endpoint does not declare", () => {
    // The client cannot smuggle an extra query parameter through: only
    // declared names are read.
    expect(
      buildPath(endpoint("list-templates"), WORKSPACE, {}, { evil: "1" }),
    ).toBe("/api/v1/marketplace/templates");
  });
});

describe("isComplete", () => {
  it("is false while a required path parameter is empty", () => {
    expect(isComplete(endpoint("get-agent"), {}, {})).toBe(false);
  });

  it("is true once it is filled", () => {
    expect(isComplete(endpoint("get-agent"), { agent_id: "a1" }, {})).toBe(true);
  });

  it("is false while a required query parameter is empty", () => {
    expect(isComplete(endpoint("search"), {}, {})).toBe(false);
    expect(isComplete(endpoint("search"), {}, { q: "sales" })).toBe(true);
  });

  it("does not require optional parameters", () => {
    expect(isComplete(endpoint("list-listings"), {}, {})).toBe(true);
  });
});
