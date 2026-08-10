"use client";

/**
 * The centre column: wordmark, tagline, the official mascot, and the
 * eight capability cards flanking it.
 *
 * Replaces a bespoke WebGL scene (a robot on a neon-city platform) with
 * the one approved mascot asset. That scene was three problems at once:
 * a second, unapproved robot illustration (docs/design/design-system.md
 * §6 fixes the mascot's identity — no surface draws its own), a
 * cyberpunk palette the brief rules out (§54), and a WebGL dependency
 * with no accessible fallback content of its own (the a11y suite only
 * passed because the canvas was `aria-hidden` and jsdom always rendered
 * the *fallback*, never the thing shipped to real users' browsers).
 *
 * The heading and the card list are what a screen reader gets from this
 * column — they carry the product claim the mascot carries visually.
 */

import { motion, useReducedMotion } from "framer-motion";

import { AgentVerseMascot } from "@/components/brand/agentverse-mascot";

import { FeatureCards, FeatureCardsCompact } from "./feature-cards";

export function AuthHero(): React.JSX.Element {
  const reduceMotion = useReducedMotion();

  return (
    <div className="relative flex w-full flex-col items-center">
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="flex flex-col items-center text-center"
      >
        <AgentVerseMascot pose="waving" className="h-40 w-auto sm:h-48" priority />
        <h2 className="mt-4 font-display text-3xl font-bold tracking-tight text-foreground lg:text-4xl">
          AgentVerse
        </h2>
        <p className="mt-1.5 text-sm text-muted-foreground lg:text-base">
          AI Workforce. Limitless Possibilities.
        </p>
      </motion.div>

      {/* Desktop: four cards each side, flanking the mascot. */}
      <div className="mt-8 hidden w-full items-start justify-between gap-6 lg:flex">
        <div className="w-[200px]">
          <FeatureCards side="left" />
        </div>
        <div className="w-[200px]">
          <FeatureCards side="right" />
        </div>
      </div>

      {/* Tablet and below: one grid, since there is no room to flank the
          mascot without crushing it. */}
      <div className="mt-6 w-full lg:hidden">
        <FeatureCardsCompact />
      </div>
    </div>
  );
}
