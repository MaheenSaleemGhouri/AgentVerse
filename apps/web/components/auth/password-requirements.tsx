"use client";

/**
 * The live "Password must contain" checklist from the signup panel.
 *
 * The rules are exported as a Zod refinement source so the checklist and
 * the submit validation cannot disagree — a list that ticks all four
 * while the server rejects the password is worse than no list at all
 * (Rule 3: one source of truth).
 *
 * Announced politely rather than assertively: this updates on every
 * keystroke, and `aria-live="assertive"` would interrupt a screen-reader
 * user mid-word on every character typed.
 */

import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

export interface PasswordRule {
  readonly label: string;
  readonly test: (value: string) => boolean;
}

export const PASSWORD_RULES: readonly PasswordRule[] = [
  { label: "At least 8 characters", test: (v) => v.length >= 8 },
  { label: "One uppercase letter", test: (v) => /[A-Z]/.test(v) },
  { label: "One number", test: (v) => /\d/.test(v) },
  { label: "One special character", test: (v) => /[^A-Za-z0-9]/.test(v) },
];

export function satisfiesAllRules(value: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(value));
}

export function PasswordRequirements({ value }: { value: string }): React.JSX.Element {
  const met = PASSWORD_RULES.filter((rule) => rule.test(value)).length;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-muted-foreground">Password must contain:</p>

      {/* Strength bar. Four segments, one per rule — a percentage would
          imply a precision the rules do not have. */}
      <div className="flex gap-1" aria-hidden="true">
        {PASSWORD_RULES.map((rule, index) => (
          <span
            key={rule.label}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors duration-300",
              index < met
                ? met === PASSWORD_RULES.length
                  ? "bg-success"
                  : met >= 3
                    ? "bg-accent-solid"
                    : "bg-warning"
                : "bg-muted"
            )}
          />
        ))}
      </div>

      <ul className="flex flex-col gap-1" aria-live="polite">
        {PASSWORD_RULES.map((rule) => {
          const passed = rule.test(value);
          return (
            <li key={rule.label} className="flex items-center gap-1.5 text-xs">
              {/* Icon *and* colour *and* the sentence below — status is
                  never colour-alone (Rule 7). */}
              {passed ? (
                <Check className="size-3 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <X className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
              )}
              <span className={passed ? "text-success-strong" : "text-muted-foreground"}>
                {rule.label}
              </span>
              <span className="sr-only">{passed ? "— met" : "— not met"}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
