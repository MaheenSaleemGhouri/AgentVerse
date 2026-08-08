import Image from "next/image";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The official AgentVerse mascot.
 *
 * One component so every appearance goes through the same approved
 * assets. `docs/design/design-system.md` §6 fixes the character's
 * identity — no surface gets to draw its own robot, and a new pose means
 * a new file in `public/brand/mascot/`, not a different illustration.
 *
 * Decorative by default. The mascot reinforces a message that the
 * surrounding copy already carries, so announcing it again is noise;
 * pass `alt` only where it is genuinely the sole carrier of meaning,
 * which should be almost nowhere.
 */

/** The poses that exist as assets. A pose not listed here has no file. */
export type MascotPose = "waving" | "happy" | "thinking" | "excited";

/** Measured from the files, not estimated — a wrong intrinsic size is a
 * layout shift on every render. */
const INTRINSIC: Record<MascotPose, { width: number; height: number }> = {
  waving: { width: 220, height: 360 },
  happy: { width: 215, height: 182 },
  thinking: { width: 195, height: 184 },
  excited: { width: 185, height: 182 },
};

export function AgentVerseMascot({
  pose,
  className,
  alt,
  priority = false,
}: {
  pose: MascotPose;
  className?: string;
  /** Omit for decorative use — the default and the common case. */
  alt?: string;
  priority?: boolean;
}): React.JSX.Element {
  const size = INTRINSIC[pose];

  return (
    <Image
      src={`/brand/mascot/${pose}.png`}
      // Intrinsic dimensions are required so the browser reserves the
      // right box before the file arrives; without them the mascot
      // landing shifts whatever sits beside it.
      width={size.width}
      height={size.height}
      alt={alt ?? ""}
      aria-hidden={alt ? undefined : true}
      priority={priority}
      className={cn("select-none", className)}
    />
  );
}
