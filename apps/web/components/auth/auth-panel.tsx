"use client";

/**
 * The card every auth surface is built from — AVDS's `Card` primitive
 * with a purposeful entrance (CLAUDE.md §15: motion communicates state
 * change, never decoration; a form appearing is a real state change).
 *
 * Not `components/ui/card.tsx` directly: the entrance animation and the
 * `elevated` treatment (a slightly heavier shadow for the panel that
 * carries the primary task on a route) are specific to this surface, so
 * they compose on top of the shared primitive rather than branching it.
 */

import { motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

import { Card } from "@/components/ui/card";

export function AuthPanel({
  children,
  className,
  elevated = false,
}: {
  children: React.ReactNode;
  className?: string;
  /** The panel actively being used on this route (vs. a preview of the
   *  other one) reads slightly closer to the surface. */
  elevated?: boolean;
}): React.JSX.Element {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="w-full"
    >
      <Card
        className={cn(
          "gap-0 px-6 py-7 sm:px-8",
          elevated ? "shadow-md" : "shadow-sm",
          className
        )}
      >
        {children}
      </Card>
    </motion.div>
  );
}
