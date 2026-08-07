import "server-only";

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

import matter from "gray-matter";

import { extractHeadings } from "./render";
import { PILLARS } from "./pillars";
import { type Guide, guideFrontmatterSchema } from "./types";

const CONTENT_ROOT = path.join(process.cwd(), "content", "docs");

/**
 * The corpus, read once per process.
 *
 * Every docs surface — the pages, the sidebar, the search index, the
 * sitemap — is derived from this one read. That is what makes adding a
 * guide a single-file change: drop a `.md` in the right pillar
 * directory and it appears in all four, with no registry to update and
 * no chance of the registry disagreeing with what is on disk.
 */
let cached: Promise<readonly Guide[]> | null = null;

export function loadGuides(): Promise<readonly Guide[]> {
  cached ??= readCorpus();
  return cached;
}

async function readCorpus(): Promise<readonly Guide[]> {
  const guides: Guide[] = [];

  for (const pillar of PILLARS) {
    const directory = path.join(CONTENT_ROOT, pillar.slug);
    const entries = await readdir(directory).catch(() => [] as string[]);

    for (const entry of entries) {
      if (!entry.endsWith(".md")) continue;
      const raw = await readFile(path.join(directory, entry), "utf8");
      const { data, content } = matter(raw);

      const parsed = guideFrontmatterSchema.safeParse(data);
      if (!parsed.success) {
        // Thrown, not warned. A guide with broken frontmatter would
        // otherwise render with a blank title and stay that way until a
        // customer found it — a build failure is the cheapest place for
        // this to surface.
        throw new Error(
          `Invalid frontmatter in content/docs/${pillar.slug}/${entry}: ${parsed.error.message}`,
        );
      }
      if (parsed.data.pillar !== pillar.slug) {
        // The directory is the source of truth for the URL, so a
        // mismatched `pillar` field would put the guide in one place in
        // the sidebar and another in its own metadata.
        throw new Error(
          `content/docs/${pillar.slug}/${entry} declares pillar "${parsed.data.pillar}" ` +
            `but lives under "${pillar.slug}".`,
        );
      }

      guides.push({
        ...parsed.data,
        slug: `${pillar.slug}/${entry.replace(/\.md$/, "")}`,
        body: content,
        headings: extractHeadings(content),
      });
    }
  }

  return sortGuides(guides);
}

/** By pillar order, then `order`, then title — fully deterministic, so
 * the sidebar does not reshuffle because a filesystem returned entries
 * in a different order. */
export function sortGuides(guides: readonly Guide[]): readonly Guide[] {
  // Keyed as `string` rather than the literal union: `Guide.pillar`
  // comes back from Zod as a validated `string`, and narrowing it here
  // would only move the cast somewhere less obvious.
  const pillarRank = new Map<string, number>(
    PILLARS.map((pillar, index) => [pillar.slug, index]),
  );
  return [...guides].sort((left, right) => {
    const byPillar =
      (pillarRank.get(left.pillar) ?? 0) - (pillarRank.get(right.pillar) ?? 0);
    if (byPillar !== 0) return byPillar;
    if (left.order !== right.order) return left.order - right.order;
    return left.title.localeCompare(right.title);
  });
}

/** Guides a reader should be shown. Drafts exist on disk but are not
 * published, so they never reach the sidebar, the sitemap or search. */
export async function loadPublishedGuides(): Promise<readonly Guide[]> {
  const guides = await loadGuides();
  return guides.filter((guide) => guide.status !== "draft");
}

export async function findGuide(slug: string): Promise<Guide | undefined> {
  const guides = await loadPublishedGuides();
  return guides.find((guide) => guide.slug === slug);
}

export interface PillarSection {
  readonly slug: string;
  readonly name: string;
  readonly description: string;
  readonly guides: readonly Guide[];
}

/** The sidebar: pillars in fixed order, empty ones omitted. */
export async function loadNav(): Promise<readonly PillarSection[]> {
  const guides = await loadPublishedGuides();
  return PILLARS.map((pillar) => ({
    ...pillar,
    guides: guides.filter((guide) => guide.pillar === pillar.slug),
  })).filter((section) => section.guides.length > 0);
}
