"use client";

/**
 * The auth panels' input: a leading icon, an optional reveal toggle, and
 * a focus glow.
 *
 * Not a variant of `components/ui/input.tsx` because that primitive is
 * themed for the light/dark product surfaces and this one lives on glass
 * over a dark 3D scene — its own token set, not a conditional inside a
 * shared component (§6: extend by composition, not by adding branches to
 * a shared primitive).
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
  ref,
) {
  const id = useId();
  const errorId = `${id}-error`;
  const [revealed, setRevealed] = useState(false);
  const resolvedType = revealable ? (revealed ? "text" : "password") : type;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-[#cfcae8]">
        {label}
      </label>

      <div className="relative">
        <Icon
          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[#8b84b0]"
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
            "w-full rounded-xl border bg-[#0f0c24]/80 py-2.5 pl-10 text-sm text-white",
            revealable ? "pr-11" : "pr-3.5",
            "placeholder:text-[#6f6892]",
            "transition-[box-shadow,border-color] duration-200",
            "focus:outline-none focus-visible:ring-[3px]",
            error
              ? "border-[#f4655b]/70 focus-visible:border-[#f4655b] focus-visible:ring-[#f4655b]/25"
              : "border-white/10 focus-visible:border-[#a855f7] focus-visible:ring-[#a855f7]/30",
            className,
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
              "absolute right-1.5 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-lg",
              "text-[#8b84b0] transition-colors hover:text-white",
              "focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40",
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
        <p id={errorId} className="text-xs text-[#f4655b]">
          {error}
        </p>
      )}
    </div>
  );
});
