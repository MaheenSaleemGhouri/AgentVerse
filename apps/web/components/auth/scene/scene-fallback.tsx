"use client";

/**
 * The hero without WebGL.
 *
 * Shown while the canvas loads, when the user prefers reduced motion,
 * on narrow viewports, and on browsers without WebGL. It is a finished
 * composition rather than a grey box: the same violet-to-cyan depth,
 * the same glowing dais, a CSS skyline. A user who only ever sees this
 * should not feel they got the broken version.
 *
 * Pure CSS — no canvas, no renderer, nothing in the bundle beyond this
 * file.
 */

import { cn } from "@/lib/utils";

export function SceneFallback({
  reducedMotion = false,
}: {
  reducedMotion?: boolean;
}): React.JSX.Element {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Depth: a violet core fading to near-black, which is what the
          fog does in the 3D scene. */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_50%_45%,rgba(124,58,237,0.34),transparent_70%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_40%_30%_at_50%_75%,rgba(34,211,238,0.20),transparent_70%)]" />

      {/* Skyline: repeating gradient bars, two bands at different
          opacities so there is parallax depth without parallax motion. */}
      <div
        className="absolute inset-x-0 bottom-[22%] h-[46%] opacity-45 [mask-image:linear-gradient(to_top,black,transparent)]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(90deg, rgba(124,58,237,0.55) 0 3px, transparent 3px 26px), repeating-linear-gradient(90deg, rgba(37,99,235,0.4) 0 5px, transparent 5px 47px)",
          backgroundSize: "auto 100%, auto 72%",
          backgroundPosition: "bottom, bottom",
          backgroundRepeat: "repeat-x",
        }}
      />
      <div
        className="absolute inset-x-0 bottom-[22%] h-[30%] opacity-25 [mask-image:linear-gradient(to_top,black,transparent)]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(90deg, rgba(192,38,211,0.5) 0 4px, transparent 4px 33px)",
          backgroundRepeat: "repeat-x",
        }}
      />

      {/* The dais, as concentric rings. Pulses only when motion is
          welcome — this is the one animated element, and it is a slow
          opacity breathe rather than movement. */}
      <div className="absolute bottom-[18%] left-1/2 -translate-x-1/2">
        <div
          className={cn(
            "size-56 rounded-full border border-[#a855f7]/40 bg-[radial-gradient(circle,rgba(168,85,247,0.35),transparent_70%)]",
            !reducedMotion && "motion-safe:animate-pulse",
          )}
        />
        <div className="absolute inset-8 rounded-full border border-[#22d3ee]/50" />
        <div className="absolute inset-16 rounded-full bg-[radial-gradient(circle,rgba(34,211,238,0.45),transparent_65%)]" />
      </div>

      {/* Floor line, echoing the reflective plane. */}
      <div className="absolute inset-x-0 bottom-[21%] h-px bg-gradient-to-r from-transparent via-[#a855f7]/60 to-transparent" />
    </div>
  );
}
