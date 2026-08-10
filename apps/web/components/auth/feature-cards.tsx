"use client";

/**
 * The eight capability cards flanking the hero mascot.
 *
 * Restrained on purpose: the previous version gave each card its own
 * infinite float and a violet glow, which is exactly the "excessive
 * animation" / "random gradients" the design brief rules out. These are
 * AVDS cards with a single settle-in on mount — motion that marks the
 * page becoming ready, not decoration that runs forever.
 *
 * They are also the page's actual product claim: a visitor who reads
 * nothing else learns what AgentVerse does from these eight items.
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
}: {
  feature: Feature;
  index: number;
}): React.JSX.Element {
  const reduceMotion = useReducedMotion();
  const Icon = feature.icon;

  return (
    <motion.li
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 + index * 0.05, ease: [0.16, 1, 0.3, 1] }}
      className="list-none"
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-card px-3.5 py-3 shadow-sm">
        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-accent text-accent-foreground">
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block text-[13px] font-semibold leading-tight text-foreground">
            {feature.title}
          </span>
          <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
            {feature.body}
          </span>
        </span>
      </div>
    </motion.li>
  );
}

export function FeatureCards({ side }: { side: "left" | "right" }): React.JSX.Element {
  const features = side === "left" ? LEFT : RIGHT;
  return (
    <ul className="flex flex-col gap-3">
      {features.map((feature, index) => (
        <FeatureCard key={feature.title} feature={feature} index={index} />
      ))}
    </ul>
  );
}

/** Every capability as one list, for the tablet and mobile layouts where
 *  there is no room to flank the mascot. */
export function FeatureCardsCompact(): React.JSX.Element {
  return (
    <ul className="grid w-full grid-cols-2 gap-3 sm:grid-cols-4">
      {[...LEFT, ...RIGHT].map((feature, index) => (
        <FeatureCard key={feature.title} feature={feature} index={index} />
      ))}
    </ul>
  );
}
