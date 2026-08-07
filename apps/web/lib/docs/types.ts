import { z } from "zod";

import { PILLAR_SLUGS } from "./pillars";

/**
 * Frontmatter, validated rather than trusted.
 *
 * A guide with a missing `title` or a pillar that does not exist should
 * fail the build, not render a page with a blank heading that nobody
 * notices until a customer reads it. Zod turns a content mistake into a
 * build error, which is the only point at which it is cheap to fix.
 */
export const guideFrontmatterSchema = z.object({
  title: z.string().min(1),
  /** The reader's goal, one sentence — used on cards and in metadata. */
  summary: z.string().min(1),
  pillar: z.enum(PILLAR_SLUGS as [string, ...string[]]),
  /**
   * The date these steps were last run against the live product.
   * `technical-writer`'s rule: a guide written from a spec is a guide
   * that describes something that may never have shipped.
   */
  last_verified: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  status: z.enum(["draft", "published", "deprecated"]),
  /** Position within its pillar. Ties fall back to title order. */
  order: z.number().int().nonnegative().default(100),
});

export type GuideFrontmatter = z.infer<typeof guideFrontmatterSchema>;

export interface Heading {
  readonly id: string;
  readonly text: string;
  readonly level: 2 | 3;
}

export interface Guide extends GuideFrontmatter {
  /** `<pillar>/<name>` — the URL path under `/docs`. */
  readonly slug: string;
  readonly body: string;
  readonly headings: readonly Heading[];
}
