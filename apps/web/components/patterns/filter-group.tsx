"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import { tabsListVariants, tabsTriggerVariants } from "@/components/ui/tabs";

/**
 * A segmented filter — visually a tab strip, semantically a group of
 * toggle buttons.
 *
 * Why this exists rather than reusing `Tabs`: a `tablist` promises that
 * each tab controls a `tabpanel`, and Radix implements that promise by
 * putting `aria-controls` on every trigger. When the filtered results are
 * rendered *outside* the `Tabs` element — as they are on the marketplace
 * and the MCP runtime view — those `aria-controls` point at panels that
 * do not exist. axe reports it as a critical `aria-valid-attr-value`
 * violation, and a screen reader announces a tab that controls nothing.
 *
 * The fix is not to silence the rule. These controls filter a list; they
 * do not switch panels. `aria-pressed` toggle buttons in a labelled group
 * say exactly that, and arrow-key roving focus is not expected of them
 * the way it is of a real tablist, so keyboard behaviour stays the plain
 * Tab-and-Enter model users already have (accessibility-expert: semantic
 * HTML before ARIA).
 *
 * Styling is shared with `Tabs` rather than copied, so the two cannot
 * drift apart visually.
 */
export function FilterGroup<T extends string>({
  label,
  value,
  onValueChange,
  options,
  className,
}: {
  /** Names the group for screen readers, e.g. "Filter by category". */
  label: string;
  value: T;
  onValueChange: (next: T) => void;
  options: ReadonlyArray<{ value: T; label: string }>;
  className?: string;
}): React.JSX.Element {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(tabsListVariants(), "h-auto flex-wrap", className)}
    >
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            // Communicates the on/off state of this specific filter.
            // `aria-selected` would be a lie outside a tablist/listbox.
            aria-pressed={isActive}
            // Drives the shared `data-[state=active]` styling, so the
            // active look comes from the same source as a real tab's.
            data-state={isActive ? "active" : "inactive"}
            onClick={() => onValueChange(option.value)}
            className={cn(tabsTriggerVariants(), "h-8 flex-none")}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
