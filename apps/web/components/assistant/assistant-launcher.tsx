"use client";

import * as React from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/**
 * The mascot, flattened to a 2D mark.
 *
 * Inline SVG on `currentColor` rather than an asset: it costs no
 * request, and it is theme-correct in both palettes without a second
 * file. The `robot.glb` scene on the auth page stays where it is —
 * loading three.js behind a floating button on every dashboard route
 * would be an absurd price for an icon.
 *
 * It is the same CC0 placeholder character noted at the start of this
 * phase, not a branded asset.
 */
function MascotMark({ className }: { className?: string }): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M12 2v3"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="12" cy="2" r="1.2" fill="currentColor" />
      <rect
        x="3.5"
        y="5"
        width="17"
        height="13"
        rx="4"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="9" cy="11.5" r="1.4" fill="currentColor" />
      <circle cx="15" cy="11.5" r="1.4" fill="currentColor" />
      <path
        d="M9.5 21h5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

const AssistantPanel = React.lazy(() =>
  import("@/components/assistant/assistant-panel").then((module) => ({
    default: module.AssistantPanel,
  }))
);

/**
 * The assistant's entry point: a small persistent button in the corner
 * of every dashboard page.
 *
 * The panel itself is lazy — it carries the streaming hook, the answer
 * renderer, and the server actions, and most page loads never open it.
 * Every route in the product would otherwise pay for a surface used on
 * a few of them (CLAUDE.md §17).
 *
 * Deliberately not a new sidebar entry: the assistant is help *about*
 * the page you are on, and sending someone to a different page to ask
 * about this one is the opposite of what it is for.
 */
export function AssistantLauncher({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const [open, setOpen] = React.useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        className="fixed right-5 bottom-5 z-40 flex size-12 items-center justify-center rounded-full border border-border bg-card shadow-lg transition-transform hover:scale-105 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none motion-reduce:transition-none motion-reduce:hover:scale-100"
        aria-label="Ask the AgentVerse assistant"
      >
        <MascotMark className="size-6 text-primary" />
      </SheetTrigger>

      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="px-4 py-3">
          <SheetTitle>AgentVerse assistant</SheetTitle>
          <SheetDescription>
            Answers from the documentation, with links back to the source.
          </SheetDescription>
        </SheetHeader>

        {/* Mounted only once opened, so the first render of the panel is
            also the first time its code is fetched. */}
        {open && (
          <React.Suspense
            fallback={<p className="p-4 text-sm text-muted-foreground">Loading…</p>}
          >
            <AssistantPanel workspaceId={workspaceId} />
          </React.Suspense>
        )}
      </SheetContent>
    </Sheet>
  );
}
