import * as React from "react";

import type { Heading } from "@/lib/docs/types";

/**
 * On-page contents.
 *
 * A plain server-rendered list of anchors — no scroll-spy. Highlighting
 * the section you happen to be scrolled past needs an observer and a
 * client boundary, and buys a reader very little that the browser's own
 * scroll position does not already tell them.
 */
export function TableOfContents({
  headings,
}: {
  headings: readonly Heading[];
}): React.JSX.Element | null {
  // One heading is not a table of contents; it is a duplicate of the
  // title with extra steps.
  if (headings.length < 2) return null;

  return (
    <nav aria-labelledby="toc-heading" className="text-sm">
      <h2
        id="toc-heading"
        className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase"
      >
        On this page
      </h2>
      <ul className="space-y-1.5 border-l border-border">
        {headings.map((heading) => (
          <li key={heading.id}>
            <a
              href={`#${heading.id}`}
              className={
                heading.level === 3
                  ? "-ml-px block border-l border-transparent py-0.5 pl-6 text-muted-foreground hover:border-foreground hover:text-foreground"
                  : "-ml-px block border-l border-transparent py-0.5 pl-3 text-muted-foreground hover:border-foreground hover:text-foreground"
              }
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
