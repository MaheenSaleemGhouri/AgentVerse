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
  // The guide corpus is read with `readdir`/`readFile` at request time,
  // and Next's file tracing only follows *statically analysable* reads.
  // A dynamically-listed directory is invisible to it, so without this
  // the `content/` markdown is omitted from the standalone output and
  // every docs route 404s in production while working perfectly in dev
  // — the worst shape of bug to find after a deploy.
  outputFileTracingIncludes: {
    "/docs": ["./content/docs/**/*"],
    "/docs/[...slug]": ["./content/docs/**/*"],
    "/sitemap.xml": ["./content/docs/**/*"],
    // The dashboard shell builds the palette's docs index too.
    "/dashboard/[workspaceId]": ["./content/docs/**/*"],
  },
};

export default nextConfig;
