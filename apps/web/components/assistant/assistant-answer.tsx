"use client";

import Link from "next/link";
import * as React from "react";

import { parseAnswer } from "@/lib/assistant/render";

/**
 * Renders one assistant answer.
 *
 * React elements, never `dangerouslySetInnerHTML` — this is model
 * output, and the only reliable way to keep markup out of it is never
 * to interpret markup at all.
 */
export function AssistantAnswer({ markdown }: { markdown: string }): React.JSX.Element {
  const blocks = React.useMemo(() => parseAnswer(markdown), [markdown]);

  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {blocks.map((block, blockIndex) =>
        block.kind === "bullet" ? (
          <p key={blockIndex} className="flex gap-2 pl-1">
            <span aria-hidden="true" className="text-muted-foreground">
              •
            </span>
            <span>
              <Inlines inlines={block.inlines} />
            </span>
          </p>
        ) : (
          <p key={blockIndex}>
            <Inlines inlines={block.inlines} />
          </p>
        )
      )}
    </div>
  );
}

function Inlines({
  inlines,
}: {
  inlines: readonly { text: string; href?: string }[];
}): React.JSX.Element {
  return (
    <>
      {inlines.map((inline, index) =>
        inline.href === undefined ? (
          <React.Fragment key={index}>{inline.text}</React.Fragment>
        ) : (
          <Link
            key={index}
            href={inline.href}
            className="font-medium text-primary underline underline-offset-2"
          >
            {inline.text}
          </Link>
        )
      )}
    </>
  );
}
