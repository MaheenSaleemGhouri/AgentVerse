import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"],
    // lib/env.ts validates at import time so a missing value fails
    // startup loudly. Component tests transitively import it, so they
    // need values present — deliberately obvious placeholders, since
    // nothing here opens a connection or signs anything. Satisfying the
    // guard is the point; relaxing env.ts for tests would weaken a
    // production behaviour to make a test convenient.
    env: {
      DATABASE_URL: "postgresql://test:test@localhost:5432/test",
      BETTER_AUTH_SECRET: "test-only-not-a-real-secret",
      BETTER_AUTH_URL: "http://localhost:3000",
      API_INTERNAL_URL: "http://localhost:8000",
      INTERNAL_API_SECRET: "test-only-not-a-real-secret",
    },
    // Pre-bundle dependencies with esbuild before the tests run.
    //
    // The suite was intermittently failing with "Failed to start forks
    // worker … Timeout waiting for worker to respond", which reads as a
    // broken test and is actually a starved one. Vitest's worker-start
    // budget is hardcoded (60s), so it cannot be raised from config —
    // the only fix is to make startup cheaper.
    //
    // The measurements point at where the time goes: ~180s of a run is
    // module *import* against ~3s of actual test execution, because the
    // repo sits on a Windows volume reached through WSL and every
    // unbundled module is a separate round trip across that boundary.
    // Capping forks to 2 and then to 1 both made it *worse*, which is
    // what ruled out jsdom count and contention as the cause. Bundling
    // the dependency graph once collapses thousands of those round trips
    // into a handful.
    //
    // This reduced the failure but has not eliminated it on a WSL-hosted
    // Windows volume, where one file still occasionally misses its start
    // window. Stated rather than left to be discovered: the suite passes
    // reliably on a native Linux filesystem, which is where CI enforces
    // it, and every file passes when run on its own. Retrying until
    // green was not done and should not be (CLAUDE.md §11) — the open
    // part of this is a slow-filesystem problem, not a test defect.
    deps: { optimizer: { web: { enabled: true } } },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // See test/server-only-stub.ts — keeps the production guard while
      // letting jsdom tests import modules that transitively touch it.
      "server-only": path.resolve(__dirname, "test/server-only-stub.ts"),
    },
  },
});
