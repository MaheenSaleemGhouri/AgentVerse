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
