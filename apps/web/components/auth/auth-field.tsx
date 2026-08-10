"use client";

/**
 * The auth panels' input: a leading icon, an optional reveal toggle, and
 * AVDS's own focus/error tokens.
 *
 * Not a variant of `components/ui/input.tsx`: that primitive has no
 * leading-icon or reveal-toggle slot, and adding both as conditional
 * props would turn a plain input into a special case for one surface
 * (§6: extend by composition, not by adding branches to a shared
 * primitive). This composes `input`'s own token set instead of forking
 * it, so the two stay visually identical everywhere but their layout.
 *
 * Accessibility is where this differs most from a decorative field:
 * every input keeps a real `<label>`, the reveal button has a name that
 * changes with its state, and the error is wired through
 * `aria-describedby` + `aria-invalid` so a screen reader gets it on
 * focus rather than only sighted users getting it in red.
 */

import { Eye, EyeOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { forwardRef, useId, useState } from "react";

import { cn } from "@/lib/utils";

interface AuthFieldProps extends Omit<React.ComponentProps<"input">, "id"> {
  label: string;
  icon: LucideIcon;
  error?: string | undefined;
  /** Renders the show/hide toggle and manages the input type. */
  revealable?: boolean;
}

export const AuthField = forwardRef<HTMLInputElement, AuthFieldProps>(function AuthField(
  { label, icon: Icon, error, revealable = false, className, type = "text", ...props },
  ref
) {
  const id = useId();
  const errorId = `${id}-error`;
  const [revealed, setRevealed] = useState(false);
  const resolvedType = revealable ? (revealed ? "text" : "password") : type;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>

      <div className="relative">
        <Icon
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          {...props}
          id={id}
          ref={ref}
          type={resolvedType}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={cn(
            "w-full rounded-md border border-input bg-background py-2 pl-9 text-sm text-foreground",
            revealable ? "pr-10" : "pr-3",
            "placeholder:text-muted-foreground",
            "transition-[box-shadow,border-color] duration-150",
            "focus:outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
            error &&
              "border-destructive focus-visible:border-destructive focus-visible:ring-destructive/25",
            className
          )}
        />

        {revealable && (
          <button
            type="button"
            onClick={() => setRevealed((value) => !value)}
            // The name states the action, and it flips with state — a
            // static "Toggle password" leaves a screen-reader user
            // unable to tell whether the password is currently exposed.
            aria-label={revealed ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            aria-pressed={revealed}
            className={cn(
              "absolute top-1/2 right-1 grid size-7 -translate-y-1/2 place-items-center rounded",
              "text-muted-foreground transition-colors hover:text-foreground",
              "focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            )}
          >
            {revealed ? (
              <EyeOff className="size-4" aria-hidden="true" />
            ) : (
              <Eye className="size-4" aria-hidden="true" />
            )}
          </button>
        )}
      </div>

      {error && (
        <p id={errorId} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
});
