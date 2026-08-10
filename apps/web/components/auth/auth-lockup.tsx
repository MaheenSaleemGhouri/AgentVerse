import Link from "next/link";

import { cn } from "@/lib/utils";

import { AgentVerseMark } from "@/components/brand/agentverse-mark";

/**
 * Mark plus wordmark for the auth surfaces, linking back to the
 * marketing home rather than sitting inert — every other lockup in the
 * product (the sidebar's) is a link too.
 *
 * Uses the one approved mark (`components/brand/agentverse-mark.tsx`),
 * not a second brand asset — the auth flow previously drew its own
 * violet-gradient triangle, which was a duplicate identity, not a
 * themed variant (Rule 3, DRY at the design level).
 */
export function AuthLockup({ className }: { className?: string }): React.JSX.Element {
  return (
    <Link
      href="/"
      className={cn(
        "inline-flex items-center gap-2.5 rounded-md focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
        className
      )}
    >
      <AgentVerseMark className="size-7 text-primary" title="AgentVerse" />
      <span className="font-display text-lg font-semibold tracking-tight text-foreground">
        AgentVerse
      </span>
    </Link>
  );
}
