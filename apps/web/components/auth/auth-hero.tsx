"use client";

/**
 * The centre column: mark, wordmark, tagline, 3D scene, and the eight
 * capability cards flanking it.
 *
 * The heading order matters more than it looks. The 3D canvas is
 * `aria-hidden`, so this `<h2>` and the card list are the *only* thing a
 * screen reader gets from the hero — they carry the product claim the
 * robot carries visually.
 */

import { motion, useReducedMotion } from "framer-motion";

import { AgentVerseMark } from "./agentverse-mark";
import { FeatureCards, FeatureCardsCompact } from "./feature-cards";
import { SceneLoader } from "./scene/scene-loader";

export function AuthHero(): React.JSX.Element {
  const reduceMotion = useReducedMotion();

  return (
    <div className="relative flex w-full flex-col items-center">
      {/* Logo + wordmark + tagline, above the scene as in the design. */}
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: -18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-10 flex flex-col items-center text-center"
      >
        <motion.div
          {...(reduceMotion
            ? {}
            : {
                animate: { y: [0, -6, 0] },
                transition: {
                  duration: 5,
                  repeat: Number.POSITIVE_INFINITY,
                  ease: "easeInOut" as const,
                },
              })}
        >
          <AgentVerseMark className="size-20 lg:size-24" glow />
        </motion.div>

        <h2 className="mt-3 text-4xl font-bold tracking-tight text-white lg:text-5xl [text-shadow:0_0_38px_rgba(168,85,247,0.65)]">
          Agent<span className="bg-gradient-to-r from-[#a855f7] to-[#22d3ee] bg-clip-text text-transparent">Verse</span>
        </h2>
        <p className="mt-1.5 text-sm text-[#c4bde4] lg:text-base">
          AI Workforce. Limitless Possibilities.
        </p>
      </motion.div>

      {/* Scene + flanking cards. The canvas is absolutely positioned
          behind the cards so they overlay it the way the design shows,
          and the wrapper reserves its height so nothing shifts when the
          renderer finishes loading (§6: avoid layout shift). */}
      <div className="relative mt-2 w-full">
        <div className="relative h-[440px] w-full lg:h-[520px]">
          <SceneLoader />

          {/* Desktop: four cards each side, vertically centred. */}
          <div className="pointer-events-none absolute inset-0 hidden items-center justify-between px-1 lg:flex">
            <div className="pointer-events-auto w-[190px]">
              <FeatureCards side="left" />
            </div>
            <div className="pointer-events-auto w-[190px]">
              <FeatureCards side="right" />
            </div>
          </div>
        </div>

        {/* Tablet and below: one grid under the scene, since there is no
            room to flank it without crushing the robot. */}
        <div className="mt-6 lg:hidden">
          <FeatureCardsCompact />
        </div>
      </div>
    </div>
  );
}
