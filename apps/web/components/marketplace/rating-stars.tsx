import { Star } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A rating, shown as stars *and* stated in text.
 *
 * The number is not decoration for the stars — it is the accessible
 * value. Filled stars are `aria-hidden`, because "four filled shapes and
 * one empty one" is not something a screen reader can usefully convey,
 * and status must never be carried by a visual treatment alone
 * (CLAUDE.md §15).
 *
 * `null` renders "Not yet rated", never zero stars. A listing nobody has
 * reviewed and a listing everyone hated are different facts, and the API
 * deliberately returns `null` rather than `0.0` so a client can tell
 * them apart.
 */
export function RatingStars({
  average,
  count,
  size = "default",
  className,
}: {
  average: number | null;
  /**
   * How many reviews the average is over. Omit for a *single* review's
   * own rating — "4.0 (1)" beside one person's review reads as a summary
   * of a population of one, which is not what it is.
   */
  count?: number;
  size?: "default" | "sm";
  className?: string;
}): React.JSX.Element {
  const starSize = size === "sm" ? "size-3.5" : "size-4";

  if (average === null || count === 0) {
    return (
      <span className={cn("text-sm text-muted-foreground", className)}>Not yet rated</span>
    );
  }

  const rounded = Math.round(average);

  return (
    <span className={cn("flex items-center gap-1.5", className)}>
      <span aria-hidden="true" className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map((position) => (
          <Star
            key={position}
            className={cn(
              starSize,
              position <= rounded
                ? "fill-warning text-warning"
                : "fill-transparent text-muted-foreground/40",
            )}
          />
        ))}
      </span>
      <span className={cn("text-muted-foreground", size === "sm" ? "text-xs" : "text-sm")}>
        {/* The accessible value. The stars above are `aria-hidden`, so
            this text is what a screen reader actually announces. */}
        {average.toFixed(1)}
        {count === undefined ? " out of 5" : ` (${String(count)})`}
      </span>
    </span>
  );
}
