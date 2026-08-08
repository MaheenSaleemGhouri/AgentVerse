/**
 * Client Components must not import *values* from `server-only` modules.
 *
 * This exists because neither `tsc` nor eslint catches it. The bundler
 * does — about eighty minutes into a production build, with an error
 * that names a file three imports away from the mistake. It has cost two
 * builds already: once when the ⌘K palette imported a label map from
 * `lib/api/search.ts`, and once when the marketplace catalog imported a
 * page-size constant from `lib/api/marketplace.ts`. Both were one
 * harmless-looking line.
 *
 * `import type` is fine and deliberately allowed — types are erased, so
 * they never reach the bundle. Only value imports pull the module in,
 * and with it `next/headers`.
 *
 * The check is first-level rather than fully transitive. Both real
 * failures were first-level, and a full module graph walk would be a
 * bundler — which is the thing whose feedback loop this is here to
 * shorten.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const SCANNED = ["app", "components", "lib"];

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

const FILES = SCANNED.flatMap((dir) => walk(path.join(ROOT, dir)));

/** Modules that declare `import "server-only"` at the top. */
const SERVER_ONLY = new Set(
  FILES.filter((file) => /^\s*import\s+["']server-only["']/m.test(readFileSync(file, "utf8")))
    // `lib/api/client.ts` → `@/lib/api/client`
    .map((file) => `@/${path.relative(ROOT, file).replace(/\.tsx?$/, "").replace(/\\/g, "/")}`),
);

/** Every import statement in a file, with whether it is type-only. */
function importsOf(source: string): { specifier: string; typeOnly: boolean }[] {
  const found: { specifier: string; typeOnly: boolean }[] = [];
  const pattern = /import\s+(type\s+)?([\s\S]*?)from\s+["']([^"']+)["']/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    const [, typeKeyword, clause, specifier] = match;
    if (specifier === undefined) continue;
    // `import { type A, type B }` is also fully erased; `import { A }`
    // or `import { CONST, type B }` is not.
    const everyNamedIsType =
      clause !== undefined &&
      clause.includes("{") &&
      clause
        .replace(/[{}]/g, "")
        .split(",")
        .map((part) => part.trim())
        .filter((part) => part !== "")
        .every((part) => part.startsWith("type "));
    found.push({ specifier, typeOnly: typeKeyword !== undefined || everyNamedIsType });
  }
  return found;
}

describe("the server-only boundary", () => {
  it("found the server-only modules to check against", () => {
    // Guards the guard: a broken discovery step would make every
    // assertion below vacuously pass.
    expect(SERVER_ONLY.size).toBeGreaterThan(0);
    expect(SERVER_ONLY).toContain("@/lib/api/client");
  });

  it("no Client Component imports a value from one", () => {
    const violations: string[] = [];

    for (const file of FILES) {
      const source = readFileSync(file, "utf8");
      if (!/^\s*["']use client["']/m.test(source)) continue;

      for (const entry of importsOf(source)) {
        if (!SERVER_ONLY.has(entry.specifier) || entry.typeOnly) continue;
        violations.push(
          `${path.relative(ROOT, file)} imports a value from ${entry.specifier} — ` +
            `use \`import type\`, or move the value to a client-safe module ` +
            `(see lib/search/kinds.ts and lib/marketplace/types.ts).`,
        );
      }
    }

    expect(violations).toEqual([]);
  });
});
