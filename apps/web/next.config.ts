import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output lets the production Docker image (infra/docker/web.Dockerfile)
  // ship only the built server + traced dependencies — no build toolchain,
  // no full node_modules — per CLAUDE.md §12's minimal-final-image rule.
  output: "standalone",
};

export default nextConfig;
