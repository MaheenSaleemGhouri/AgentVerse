"use client";

/**
 * The eight holographic capability cards flanking the robot.
 *
 * DOM rather than 3D geometry, deliberately: the reference shows them as
 * flat panels facing the viewer, so rendering them in the scene would
 * cost text-in-WebGL (blurry, unselectable, invisible to a screen
 * reader) for no visual gain. As DOM they are real text — readable,
 * translatable, and announced.
 *
 * They are also the page's actual product claim, which is why they are
 * a list rather than decoration: a visitor who reads nothing else
 * learns what AgentVerse does from these eight items.
 */

import { motion, useReducedMotion } from "framer-motion";
import {
  BarChart3,
  BookOpen,
  Bot,
  Globe,
  Plug,
  ShieldCheck,
  Users,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface Feature {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly body: string;
}

const LEFT: readonly Feature[] = [
  { icon: Bot, title: "AI Agents", body: "Create intelligent autonomous agents" },
  { icon: BookOpen, title: "Knowledge & RAG", body: "Bring your data. Get answers." },
  { icon: Users, title: "Team Collaboration", body: "Work together seamlessly" },
  { icon: ShieldCheck, title: "Secure & Scalable", body: "Enterprise grade security" },
];

const RIGHT: readonly Feature[] = [
  { icon: Plug, title: "MCP Integrations", body: "Connect 100+ tools & services" },
  { icon: Workflow, title: "Multi-Agent Teams", body: "Orchestrate AI workforces" },
  { icon: BarChart3, title: "Real-time Insights", body: "Monitor, analyze & optimize" },
  { icon: Globe, title: "Global Infrastructure", body: "99.9% uptime guaranteed" },
];

function FeatureCard({
  feature,
  index,
  side,
}: {
  feature: Feature;
  index: number;
  side: "left" | "right";
}): React.JSX.Element {
  const reduceMotion = useReducedMotion();
  const Icon = feature.icon;

  return (
    <motion.li
      initial={reduceMotion ? false : { opacity: 0, x: side === "left" ? -28 : 28 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6, delay: 0.25 + index * 0.09, ease: [0.16, 1, 0.3, 1] }}
      className="list-none"
    >
      <motion.div
        // Each card drifts on its own phase — a shared one would make
        // eight cards move as a single block, which reads as the page
        // scrolling rather than the cards floating.
        //
        // Spread rather than `animate={undefined}`: `tsconfig` sets
        // `exactOptionalPropertyTypes`, so an explicit undefined is not
        // the same as an absent prop.
        {...(reduceMotion
          ? {}
          : {
              animate: { y: [0, -7, 0] },
              transition: {
                duration: 5.5 + index * 0.7,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut" as const,
                delay: index * 0.45,
              },
            })}
        className={cn(
          "group relative rounded-2xl p-px",
          "bg-[linear-gradient(140deg,rgba(168,85,247,0.5),rgba(34,211,238,0.14)_50%,rgba(168,85,247,0.28))]",
          "transition-transform duration-300 hover:scale-[1.03]",
        )}
      >
        <div
          className={cn(
            "flex items-start gap-3 rounded-[calc(1rem-1px)] px-3.5 py-3",
            "bg-[linear-gradient(150deg,rgba(24,17,55,0.88),rgba(11,9,28,0.94))] backdrop-blur-xl",
            "shadow-[0_4px_30px_-8px_rgba(124,58,237,0.6)]",
          )}
        >
          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-[#7c3aed]/18 ring-1 ring-[#a855f7]/35">
            <Icon className="size-4 text-[#c4b5fd]" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="block text-[13px] font-semibold leading-tight text-white">
              {feature.title}
            </span>
            <span className="mt-0.5 block text-[11px] leading-snug text-[#a8a2c8]">
              {feature.body}
            </span>
          </span>
        </div>
      </motion.div>
    </motion.li>
  );
}

export function FeatureCards({ side }: { side: "left" | "right" }): React.JSX.Element {
  const features = side === "left" ? LEFT : RIGHT;
  return (
    <ul className="flex flex-col gap-3">
      {features.map((feature, index) => (
        <FeatureCard key={feature.title} feature={feature} index={index} side={side} />
      ))}
    </ul>
  );
}

/** Every capability as one list, for the tablet and mobile layouts where
 *  there is no room to flank the robot. */
export function FeatureCardsCompact(): React.JSX.Element {
  return (
    <ul className="grid w-full grid-cols-2 gap-3 sm:grid-cols-4">
      {[...LEFT, ...RIGHT].map((feature, index) => (
        <FeatureCard key={feature.title} feature={feature} index={index} side="left" />
      ))}
    </ul>
  );
}
