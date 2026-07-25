import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output lets the production Docker image (infra/docker/web.Dockerfile)
  // ship only the built server + traced dependencies — no build toolchain,
  // no full node_modules — per CLAUDE.md §12's minimal-final-image rule.
  output: "standalone",
  // @agentverse/contracts ships TS source, not a pre-built dist/ — this
  // lets Next's bundler compile it directly, so CI/dev never need to
  // build contracts before web (avoids a cross-package build-order
  // dependency; tsconfig.json's `paths` does the same for type-checking).
  transpilePackages: ["@agentverse/contracts"],
};

export default nextConfig;
