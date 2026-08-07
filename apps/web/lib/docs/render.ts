import "server-only";

import rehypePrettyCode from "rehype-pretty-code";
import rehypeSlug from "rehype-slug";
import rehypeStringify from "rehype-stringify";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";

/**
 * Markdown to HTML, entirely at build time.
 *
 * `server-only` is not decoration: Shiki carries a grammar and two
 * themes, and a stray client import would put a syntax highlighter in
 * the browser bundle to render text that was already final before the
 * page was built.
 *
 * Both themes are emitted at once, as CSS variables on the same markup,
 * so the light/dark toggle is a CSS switch rather than a re-highlight —
 * and code blocks are correct on first paint in either theme instead of
 * flashing the wrong one.
 */
const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype)
  // Adds `id`s to headings, which is what the on-page table of contents
  // and any `#anchor` link a reader shares both depend on.
  .use(rehypeSlug)
  .use(rehypePrettyCode, {
    theme: { light: "github-light", dark: "github-dark-dimmed" },
    defaultLang: "text",
    keepBackground: false,
  })
  .use(rehypeStringify);

export async function renderMarkdown(markdown: string): Promise<string> {
  const file = await processor.process(markdown);
  return String(file);
}

/**
 * Headings for the on-page contents, read from the source rather than
 * from the rendered HTML.
 *
 * Only `##` and `###`: `#` is the page title (rendered from frontmatter,
 * not the body), and anything deeper than `###` makes a table of
 * contents longer than the section it indexes.
 *
 * Fenced code blocks are stripped first — a `# comment` on the first
 * line of a shell sample is not a heading, and a contents list that
 * says "install the CLI" because a sample said `# install the CLI` is a
 * confusing bug to track down.
 */
export function extractHeadings(markdown: string): { id: string; text: string; level: 2 | 3 }[] {
  const withoutCode = markdown.replace(/^```[\s\S]*?^```/gm, "");
  const headings: { id: string; text: string; level: 2 | 3 }[] = [];

  for (const line of withoutCode.split("\n")) {
    const match = /^(#{2,3})\s+(.*)$/.exec(line);
    if (!match) continue;
    const [, hashes, rawText] = match;
    if (hashes === undefined || rawText === undefined) continue;
    const text = rawText.replace(/`/g, "").trim();
    headings.push({
      id: slugifyHeading(text),
      text,
      level: hashes.length === 2 ? 2 : 3,
    });
  }

  return headings;
}

/**
 * Mirrors `rehype-slug`'s output for the headings we generate.
 *
 * These two must agree: the contents list links to `#id` and the
 * rendered heading carries the `id`. They are separate implementations
 * because `rehype-slug` runs over HTML and this runs over source — the
 * unit tests pin that they still produce the same slug.
 */
export function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");
}
