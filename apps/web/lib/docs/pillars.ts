/**
 * The documentation's top-level structure.
 *
 * Five pillars, matching the product's own information architecture —
 * not the backend's service boundaries. A reader looking for how to
 * connect a tool is thinking "Agent Builder", not "integration service",
 * and documentation organized around internal module names is organized
 * for the people who wrote it rather than the people reading it.
 */

export const PILLARS = [
  {
    slug: "agent-builder",
    name: "Agent Builder",
    description: "Define an agent: its instructions, model, tools, and knowledge.",
  },
  {
    slug: "orchestration",
    name: "Orchestration",
    description: "Run agents, compose them into teams, and hand work between them.",
  },
  {
    slug: "observability",
    name: "Observability",
    description: "Watch a run happen, read its trace, and understand what it cost.",
  },
  {
    slug: "marketplace",
    name: "Marketplace",
    description: "Install a template, publish a listing, and manage versions.",
  },
  {
    slug: "platform",
    name: "Platform",
    description: "Workspaces, roles, API keys, webhooks, billing, and the SDKs.",
  },
] as const;

export type PillarSlug = (typeof PILLARS)[number]["slug"];

export const PILLAR_SLUGS: readonly PillarSlug[] = PILLARS.map((pillar) => pillar.slug);

export function pillarBySlug(slug: string): (typeof PILLARS)[number] | undefined {
  return PILLARS.find((pillar) => pillar.slug === slug);
}
