import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The AgentVerse mark — the rounded triangle-in-a-circle emblem from the
 * approved reference (panel 01, and on the mascot's chest in
 * `docs/design/mascot-reference.png`).
 *
 * Inline SVG on `currentColor` rather than an image file: it costs no
 * request, scales without a second asset, and inherits whatever surface
 * it sits on — which matters because it appears on the dark sidebar, on
 * light cards, and inside the mascot, all in the same product.
 *
 * `aria-hidden` by default. The mark is always accompanied by the
 * wordmark or by a labelled link, so announcing it a second time is
 * noise; pass a `title` where it genuinely stands alone.
 */
export function AgentVerseMark({
  className,
  title,
}: {
  className?: string;
  title?: string;
}): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      className={cn("text-sidebar-rail", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : "true"}
      aria-label={title}
    >
      <rect
        x="1.25"
        y="1.25"
        width="29.5"
        height="29.5"
        rx="9"
        stroke="currentColor"
        strokeWidth="2.5"
      />
      {/* The chevron, drawn with a rounded join so it matches the
          mascot's emblem rather than reading as a sharp arrow. */}
      <path
        d="M9.5 22.5 16 9.5l6.5 13"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M12.75 19.25h6.5"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
