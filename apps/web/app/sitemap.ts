import type { MetadataRoute } from "next";

import { loadPublishedGuides } from "@/lib/docs/loader";

/**
 * The sitemap, driven by the live guide corpus.
 *
 * Generated rather than hand-listed for the same reason the sidebar is:
 * a hand-maintained list drifts, and a sitemap that names a page that no
 * longer exists is worse than one that omits it. Only public,
 * unauthenticated routes appear — dashboard pages are per-user and must
 * never be indexed.
 *
 * Draft guides are excluded because `loadPublishedGuides` excludes them,
 * so unfinished writing cannot be indexed by being merged early.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env["NEXT_PUBLIC_SITE_URL"] ?? "https://agentverse.dev";
  const guides = await loadPublishedGuides();

  return [
    { url: `${base}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/pricing`, changeFrequency: "weekly", priority: 0.8 },
    { url: `${base}/docs`, changeFrequency: "weekly", priority: 0.8 },
    ...guides.map((guide) => ({
      url: `${base}/docs/${guide.slug}`,
      lastModified: new Date(guide.last_verified),
      changeFrequency: "monthly" as const,
      priority: 0.6,
    })),
  ];
}
