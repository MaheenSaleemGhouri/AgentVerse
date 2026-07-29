"use client";

/**
 * The gradient submit button and the social sign-in buttons.
 *
 * The social buttons are rendered from what the *server* says is
 * configured (`lib/auth.ts` only registers a provider when its client id
 * and secret are present). A provider that is not wired renders nothing
 * rather than a button that fails on click — a dead OAuth button is the
 * "mock authentication" the brief rules out, whatever it looks like.
 */

import { motion, useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Framer's `motion.button` redefines the drag and animation event
 * handlers, and `style`, with its own signatures — so the native ones
 * are omitted here rather than cast away. A cast would compile and then
 * hand the wrong event shape to any caller that passed `onDrag`.
 *
 * `style` is dropped rather than re-typed: every visual choice on this
 * button is a token-driven class, and an inline-style escape hatch is
 * exactly how a bespoke one-off gets in (§15).
 */
type GradientButtonProps = Omit<
  React.ComponentProps<"button">,
  "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd" | "style"
> & {
  icon?: LucideIcon;
  pending?: boolean;
  pendingLabel?: string;
};

export function GradientButton({
  children,
  icon: Icon,
  pending = false,
  pendingLabel,
  className,
  ...props
}: GradientButtonProps): React.JSX.Element {
  const reduceMotion = useReducedMotion();

  return (
    <motion.button
      {...(reduceMotion || pending
        ? {}
        : {
            whileHover: { scale: 1.015 },
            whileTap: { scale: 0.985 },
            transition: { type: "spring" as const, stiffness: 400, damping: 28 },
          })}
      disabled={pending || props.disabled}
      {...props}
      className={cn(
        "group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl px-4 py-2.5",
        "bg-[linear-gradient(100deg,#7c3aed,#a855f7_45%,#6366f1)]",
        "text-sm font-semibold text-white",
        "shadow-[0_6px_28px_-6px_rgba(124,58,237,0.85)]",
        "transition-shadow hover:shadow-[0_8px_36px_-4px_rgba(168,85,247,0.95)]",
        "focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/50 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f0c24]",
        "disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none",
        className,
      )}
    >
      {/* Sheen sweep on hover. Transform-only, so it never triggers
          layout (§6: high-frequency surfaces animate transform/opacity). */}
      {!reduceMotion && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -translate-x-full bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.28),transparent)] transition-transform duration-700 group-hover:translate-x-full"
        />
      )}
      {pending ? (
        <>
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          {pendingLabel ?? children}
        </>
      ) : (
        <>
          {children}
          {Icon && <Icon className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />}
        </>
      )}
    </motion.button>
  );
}

function GoogleGlyph(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.5-5.2 3.5-8.8Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.2 0 5.9-1.1 7.9-2.9l-3.9-3a7.2 7.2 0 0 1-10.7-3.8H1.3v3.1A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.3 14.3a7.1 7.1 0 0 1 0-4.6V6.6H1.3a12 12 0 0 0 0 10.8l4-3.1Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.8c1.8 0 3.4.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1A7.2 7.2 0 0 1 12 4.8Z"
      />
    </svg>
  );
}

function GitHubGlyph(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="size-4 fill-white" aria-hidden="true">
      <path d="M12 .5A11.5 11.5 0 0 0 .4 12.1c0 5.1 3.3 9.5 7.9 11 .6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.4-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.7.2 2.9.1 3.2.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6a11.6 11.6 0 0 0 7.9-11A11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}

export function SocialButton({
  provider,
  onClick,
  disabled,
}: {
  provider: "google" | "github";
  onClick: () => void;
  disabled?: boolean;
}): React.JSX.Element {
  const label = provider === "google" ? "Continue with Google" : "Continue with GitHub";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex w-full items-center justify-center gap-2.5 rounded-xl px-4 py-2.5",
        "border border-white/10 bg-white/[0.04] text-sm font-medium text-white",
        "transition-colors hover:border-white/20 hover:bg-white/[0.08]",
        "focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40",
        "disabled:cursor-not-allowed disabled:opacity-50",
      )}
    >
      {provider === "google" ? <GoogleGlyph /> : <GitHubGlyph />}
      {label}
    </button>
  );
}

export function OrDivider(): React.JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <span className="h-px flex-1 bg-white/10" />
      <span className="text-[11px] font-medium tracking-widest text-[#7d76a3]">OR</span>
      <span className="h-px flex-1 bg-white/10" />
    </div>
  );
}
