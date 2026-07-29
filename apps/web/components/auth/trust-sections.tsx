"use client";

/**
 * The two strips below the auth panels: the "trusted by" logo row and
 * the six-item trust bar.
 *
 * ## A deliberate change from the reference
 *
 * The approved design shows Microsoft, Google, AWS, OpenAI, NVIDIA, and
 * Vercel under "Trusted by innovators worldwide". Those are not
 * AgentVerse customers, and the reference is concept art — shipping it
 * literally would put a false claim on the front door of the product,
 * using other companies' trademarks to make it.
 *
 * `CLAUDE.md` §2 requires every factual claim in customer-facing copy to
 * be verifiable against the shipped product, so the row is reframed to
 * what is actually true: the technologies AgentVerse is built on. Same
 * position, same visual weight, same six slots — a claim that survives
 * being read closely.
 *
 * Swap in real customer logos the moment there are real customers who
 * have agreed to be named.
 */

import { motion, useReducedMotion } from "framer-motion";
import { Blocks, Code2, Headphones, Gauge, ShieldCheck, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface TrustItem {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly body: string;
}

const TRUST: readonly TrustItem[] = [
  {
    icon: ShieldCheck,
    title: "Enterprise Security",
    body: "End-to-end encryption & compliance ready",
  },
  { icon: Gauge, title: "99.9% Uptime", body: "Built on robust global infrastructure" },
  { icon: Zap, title: "Blazing Fast", body: "Real-time streaming & instant responses" },
  { icon: Blocks, title: "Customizable", body: "Fully customizable to your needs" },
  { icon: Code2, title: "Developer Friendly", body: "APIs, SDKs & webhooks ready to integrate" },
  { icon: Headphones, title: "24/7 Support", body: "We're here to power your AI journey" },
];

const BUILT_ON = [
  "OpenAI Agents SDK",
  "Model Context Protocol",
  "PostgreSQL",
  "Redis",
  "FastAPI",
  "Next.js",
] as const;

export function BuiltOnStrip(): React.JSX.Element {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-6 py-4 backdrop-blur-xl">
      <p className="text-center text-[11px] font-medium tracking-wide text-[#8b84b0]">
        Built on the open standards teams already trust
      </p>
      <ul className="mt-3 flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
        {BUILT_ON.map((name) => (
          <li key={name} className="text-sm font-semibold text-[#cfcae8]/85">
            {name}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TrustBar(): React.JSX.Element {
  const reduceMotion = useReducedMotion();

  return (
    <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/[0.06] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {TRUST.map((item, index) => {
        const Icon = item.icon;
        return (
          <motion.li
            key={item.title}
            initial={reduceMotion ? false : { opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.45, delay: index * 0.06 }}
            className="flex items-start gap-3 bg-[#0b0920]/90 px-5 py-4 backdrop-blur-xl"
          >
            <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-[#7c3aed]/18 ring-1 ring-[#a855f7]/30">
              <Icon className="size-4 text-[#c4b5fd]" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold text-white">{item.title}</span>
              <span className="mt-0.5 block text-[11px] leading-snug text-[#8b84b0]">
                {item.body}
              </span>
            </span>
          </motion.li>
        );
      })}
    </ul>
  );
}
