import * as React from "react";

import { cn } from "@/lib/utils";

import { AgentVerseMascot, type MascotPose } from "@/components/brand/agentverse-mascot";

/**
 * Empty states teach and prompt the next action — never a bare "No data"
 * (CLAUDE.md §6/§15, `ux-designer`). If a screen can be empty, there is
 * always something the user could do about it, so `action` is expected
 * in practice even though it is optional in the type.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  mascot,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
  /**
   * Swaps the generic icon for the mascot, in the given pose. Reserved
   * for the handful of true first-run moments — an empty workspace with
   * no agents at all, say — never every empty list in the product.
   * docs/design/design-system.md §6: "use it intentionally... do not
   * force it into every component." A search-with-no-results or a
   * filtered-to-nothing state stays on the plain icon.
   */
  mascot?: MascotPose;
}): React.JSX.Element {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-4 rounded-xl border border-dashed border-border bg-card/40 px-6 py-16 text-center",
        className
      )}
    >
      {mascot ? (
        <AgentVerseMascot pose={mascot} className="h-24 w-auto" />
      ) : (
        <span className="flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Icon className="size-6" aria-hidden="true" />
        </span>
      )}
      <div className="space-y-1">
        <p className="font-medium text-foreground">{title}</p>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}
