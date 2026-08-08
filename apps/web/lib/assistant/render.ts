/**
 * The narrow slice of markdown the assistant is instructed to produce:
 * paragraphs, list items, and inline links.
 *
 * A markdown library would be the obvious reach, and it is the wrong
 * one here. This renders *model output* into a surface that sits on
 * every dashboard page — pulling a parser plus its sanitiser into that
 * bundle to support emphasis nobody asked for is weight on every route.
 * Parsing exactly what the prompt asks for, and showing anything else
 * as the literal text it is, keeps the failure mode boring: a stray
 * backtick renders as a backtick.
 *
 * No HTML is produced. The parser returns data, the component renders
 * React elements, and there is no `dangerouslySetInnerHTML` anywhere in
 * the path — which is what makes this safe against a model that decides
 * to emit a `<script>` tag.
 */

export type Inline = { readonly text: string; readonly href?: string };

export interface Block {
  readonly kind: "paragraph" | "bullet";
  readonly inlines: readonly Inline[];
}

const LINK = /\[([^\]]+)\]\(([^)\s]+)\)/g;

/**
 * Only in-app documentation links survive as links.
 *
 * The assistant is told to cite the passage URLs it was given, all of
 * which are `/docs/...` paths. Anything else — a model-invented
 * `http://` URL, a `javascript:` payload — renders as plain text
 * instead. Allowlisting the one shape that should ever appear is
 * cheaper to reason about than trying to spot the bad ones.
 */
function safeHref(raw: string): string | undefined {
  return /^\/docs\/[A-Za-z0-9\-/#]*$/.test(raw) ? raw : undefined;
}

export function parseInlines(line: string): Inline[] {
  const inlines: Inline[] = [];
  let cursor = 0;

  LINK.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = LINK.exec(line)) !== null) {
    const [full, label, url] = match;
    if (label === undefined || url === undefined) continue;
    if (match.index > cursor) {
      inlines.push({ text: line.slice(cursor, match.index) });
    }
    const href = safeHref(url);
    inlines.push(href === undefined ? { text: full } : { text: label, href });
    cursor = match.index + full.length;
  }

  if (cursor < line.length) {
    inlines.push({ text: line.slice(cursor) });
  }
  return inlines;
}

export function parseAnswer(markdown: string): Block[] {
  const blocks: Block[] = [];

  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trim();
    if (line === "") continue;

    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet?.[1] !== undefined) {
      blocks.push({ kind: "bullet", inlines: parseInlines(bullet[1]) });
      continue;
    }
    blocks.push({ kind: "paragraph", inlines: parseInlines(line) });
  }

  return blocks;
}
