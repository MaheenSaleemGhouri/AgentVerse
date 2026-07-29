/**
 * The AgentVerse mark: nested triangles in a violet-to-cyan gradient,
 * as in the approved design.
 *
 * Inline SVG rather than an image file so it scales without a raster,
 * inherits the page's glow via CSS filters, and can be recoloured per
 * surface. The gradient id is suffixed per instance — two marks on one
 * page (the reference shows three) sharing an id would make the second
 * pick up the first's gradient.
 */

import { useId } from "react";

import { cn } from "@/lib/utils";

export function AgentVerseMark({
  className,
  glow = false,
}: {
  className?: string;
  glow?: boolean;
}): React.JSX.Element {
  const id = useId();
  const gradient = `av-mark-${id}`;

  return (
    <svg
      viewBox="0 0 64 64"
      role="img"
      aria-label="AgentVerse"
      className={cn(
        "shrink-0",
        glow && "[filter:drop-shadow(0_0_18px_rgba(168,85,247,0.75))]",
        className,
      )}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#c084fc" />
          <stop offset="45%" stopColor="#7c3aed" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      {/* Outer rounded triangle. */}
      <path
        d="M32 5.5 58 50a5 5 0 0 1-4.3 7.5H10.3A5 5 0 0 1 6 50Z"
        fill="none"
        stroke={`url(#${gradient})`}
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      {/* Inner triangle, the negative space of the mark. */}
      <path
        d="M32 22 45.5 46H18.5Z"
        fill="none"
        stroke={`url(#${gradient})`}
        strokeWidth="4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Mark plus wordmark, with "Agent" in white and "Verse" in violet —
 *  the lockup used on both panels in the reference. */
export function AgentVerseLockup({ className }: { className?: string }): React.JSX.Element {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <AgentVerseMark className="size-7" glow />
      <span className="text-xl font-semibold tracking-tight text-white">
        Agent<span className="text-[#a855f7]">Verse</span>
      </span>
    </div>
  );
}
