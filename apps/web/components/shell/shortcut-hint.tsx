"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The ⌘K / Ctrl K hint on the search affordance.
 *
 * Rendered blank on the server and filled in after mount, because the
 * platform is only knowable in the browser and guessing on the server
 * produces a hydration mismatch. Reserving the width up front means the
 * hint appearing does not nudge the button.
 *
 * The palette itself already accepts either modifier
 * (`command-palette.tsx`) — this only labels it correctly, so a Windows
 * user is not told to press a key their keyboard does not have.
 */
export function ShortcutHint({ className }: { className?: string }): React.JSX.Element {
  const [label, setLabel] = React.useState<string | null>(null);

  React.useEffect(() => {
    const platform =
      typeof navigator === "undefined"
        ? ""
        : // `userAgentData` is not in every browser's lib.dom yet, and
          // `platform` is deprecated but still the reliable read here.
          `${navigator.platform ?? ""} ${navigator.userAgent ?? ""}`;
    setLabel(/mac|iphone|ipad|ipod/i.test(platform) ? "⌘K" : "Ctrl K");
  }, []);

  return (
    <kbd
      // The shortcut duplicates a button that is already labelled, so
      // announcing "Ctrl K" as text would just make the button's name
      // longer without telling a screen-reader user anything they can
      // act on differently.
      aria-hidden="true"
      className={cn(
        "inline-flex min-w-[2.75rem] justify-center rounded border border-border bg-muted px-1 font-mono text-[10px] leading-4",
        className
      )}
    >
      {label ?? " "}
    </kbd>
  );
}
