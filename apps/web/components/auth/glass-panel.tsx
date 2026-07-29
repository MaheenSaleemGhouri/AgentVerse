"use client";

/**
 * The glassmorphism card both auth panels are built from.
 *
 * Three layers make the effect read as glass rather than as a
 * translucent div: a blurred backdrop, a hairline gradient border that
 * catches "light" at the top-left, and an inner highlight. The reference
 * also tilts each panel slightly toward the centre, which is the detail
 * that makes the composition feel three-dimensional rather than flat —
 * that is `tilt`, and it is dropped under reduced motion and on narrow
 * viewports where a rotated card would clip.
 */

import { motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

export function GlassPanel({
  children,
  tilt = "none",
  className,
}: {
  children: React.ReactNode;
  /** Which way the panel leans toward the hero. */
  tilt?: "left" | "right" | "none";
  className?: string;
}): React.JSX.Element {
  const reduceMotion = useReducedMotion();
  const rotate = tilt === "left" ? 2.2 : tilt === "right" ? -2.2 : 0;

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 24, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "relative w-full rounded-3xl p-px",
        // The border is a gradient behind the card rather than a
        // `border` property, so it can fade around the perimeter the way
        // a lit edge does.
        "bg-[linear-gradient(145deg,rgba(168,85,247,0.55),rgba(34,211,238,0.18)_35%,rgba(255,255,255,0.04)_60%,rgba(168,85,247,0.35))]",
        "shadow-[0_8px_60px_-12px_rgba(124,58,237,0.55),0_0_120px_-40px_rgba(34,211,238,0.4)]",
        className,
      )}
      {...(rotate && !reduceMotion
        ? { style: { transform: `perspective(1400px) rotateY(${rotate}deg)` } }
        : {})}
    >
      <div
        className={cn(
          "relative overflow-hidden rounded-[calc(1.5rem-1px)]",
          "bg-[linear-gradient(160deg,rgba(23,17,52,0.92),rgba(10,8,26,0.96))]",
          "backdrop-blur-2xl",
          "px-7 py-8 sm:px-8",
        )}
      >
        {/* Inner top highlight — the "light source" the glass catches. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/35 to-transparent" />
        <div className="pointer-events-none absolute -top-24 left-1/2 h-48 w-[120%] -translate-x-1/2 bg-[radial-gradient(ellipse_at_center,rgba(168,85,247,0.22),transparent_70%)]" />
        {children}
      </div>
    </motion.div>
  );
}
