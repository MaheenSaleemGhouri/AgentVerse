"use client";

/**
 * Decides whether the 3D hero mounts, and keeps its weight out of every
 * bundle that does not need it.
 *
 * Three things gate the canvas, in order:
 *
 * 1. **`prefers-reduced-motion`** — the scene is continuous parallax,
 *    drifting particles, and moving vehicles. `CLAUDE.md` §6 requires a
 *    *verified* fallback, not a paused canvas, so the whole thing is
 *    replaced by the static gradient rather than mounted and stilled.
 * 2. **WebGL availability** — a browser without it would otherwise get
 *    a blank rectangle where the hero should be.
 * 3. **Viewport** — below the tablet breakpoint the design collapses to
 *    a single auth card, and a phone should not download 900 kB of
 *    renderer to draw a background it barely shows.
 *
 * The fallback is not a placeholder: it is the same composition in CSS,
 * so a user who never sees the canvas still gets a finished page rather
 * than an obviously degraded one.
 */

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { SceneFallback } from "./scene-fallback";

// `ssr: false` is required, not stylistic — three touches `window` at
// module scope. Loading is the CSS composition, so there is no flash of
// empty space while ~900 kB arrives.
const AuthScene = dynamic(() => import("./auth-scene").then((m) => m.AuthScene), {
  ssr: false,
  loading: () => <SceneFallback />,
});

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext("webgl2") ?? canvas.getContext("webgl")),
    );
  } catch {
    return false;
  }
}

export function SceneLoader(): React.JSX.Element {
  // Starts false so the server render and the first client render agree
  // on the fallback; the canvas is an enhancement applied after mount.
  const [enabled, setEnabled] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const wide = window.matchMedia("(min-width: 768px)");

    const evaluate = (): void => {
      setReducedMotion(motion.matches);
      setEnabled(!motion.matches && wide.matches && hasWebGL());
    };

    evaluate();
    // Re-evaluated on change so toggling the OS setting takes effect
    // without a reload — the check a reduced-motion audit actually makes.
    motion.addEventListener("change", evaluate);
    wide.addEventListener("change", evaluate);
    return () => {
      motion.removeEventListener("change", evaluate);
      wide.removeEventListener("change", evaluate);
    };
  }, []);

  if (!enabled) return <SceneFallback reducedMotion={reducedMotion} />;
  return <AuthScene reducedMotion={false} />;
}
