import "server-only";

import { loadPublishedGuides } from "./loader";
import type { DocsSearchEntry } from "./match";
import { pillarBySlug } from "./pillars";

/**
 * The search index, built from the same corpus the pages render.
 *
 * Body text is deliberately excluded. Indexing full guide bodies would
 * multiply the payload every reader downloads by an order of magnitude
 * to make queries match prose that is rarely what someone is looking
 * for — titles, headings and summaries are what a reader is actually
 * navigating by.
 */
export async function buildDocsSearchIndex(): Promise<readonly DocsSearchEntry[]> {
  const guides = await loadPublishedGuides();
  return guides.map((guide) => ({
    slug: guide.slug,
    title: guide.title,
    summary: guide.summary,
    pillar: guide.pillar,
    pillarName: pillarBySlug(guide.pillar)?.name ?? guide.pillar,
    headings: guide.headings.map((heading) => heading.text),
  }));
}
