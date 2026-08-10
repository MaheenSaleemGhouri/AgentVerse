"use client";

/**
 * The primary submit button and the social sign-in buttons for the auth
 * panels.
 *
 * The social buttons are rendered from what the *server* says is
 * configured (`lib/auth.ts` only registers a provider when its client id
 * and secret are present). A provider that is not wired renders nothing
 * rather than a button that fails on click — a dead OAuth button is the
 * "mock authentication" the brief rules out, whatever it looks like.
 */

import { Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";

type AuthSubmitButtonProps = React.ComponentProps<"button"> & {
  icon?: LucideIcon;
  pending?: boolean;
  pendingLabel?: string;
};

/** The one primary-action button every auth form submits through — AVDS's
 *  own `Button` primitive at `size="lg"`, not a bespoke gradient button.
 *  The previous version painted its own violet gradient outside the
 *  token system; this one is `--primary`, which already themes correctly
 *  in both light and dark (§16: one source of truth for buttons). */
export function AuthSubmitButton({
  children,
  icon: Icon,
  pending = false,
  pendingLabel,
  className,
  disabled,
  ...props
}: AuthSubmitButtonProps): React.JSX.Element {
  return (
    <Button
      type="submit"
      size="lg"
      disabled={pending || disabled}
      className={cn("w-full", className)}
      {...props}
    >
      {pending ? (
        <>
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          {pendingLabel ?? children}
        </>
      ) : (
        <>
          {children}
          {Icon && <Icon className="size-4" aria-hidden="true" />}
        </>
      )}
    </Button>
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
    <svg viewBox="0 0 24 24" className="size-4 fill-foreground" aria-hidden="true">
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
    <Button type="button" variant="outline" size="lg" onClick={onClick} disabled={disabled} className="w-full">
      {provider === "google" ? <GoogleGlyph /> : <GitHubGlyph />}
      {label}
    </Button>
  );
}

export function OrDivider(): React.JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <span className="h-px flex-1 bg-border" />
      <span className="text-[11px] font-medium tracking-widest text-muted-foreground">OR</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
