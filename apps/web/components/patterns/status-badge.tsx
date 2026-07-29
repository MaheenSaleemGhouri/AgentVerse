import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The one status vocabulary in the product. A "success" here is the same
 * token as a success `Alert` or a success `Progress` tone — no screen
 * redefines its own green (senior-ui-designer: never a second success
 * green).
 *
 * Every tone pairs a colour with a dot *and* a text label, so status is
 * never conveyed by colour alone (Rule 7).
 */
const statusVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "border-border bg-muted text-muted-foreground",
        info: "border-info/30 bg-info-soft text-info-strong",
        success: "border-success/30 bg-success-soft text-success-strong",
        warning: "border-warning/30 bg-warning-soft text-warning-strong",
        danger: "border-destructive/30 bg-destructive-soft text-destructive-strong",
        brand: "border-primary/30 bg-accent text-accent-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  }
);

const dotVariants = cva("size-1.5 shrink-0 rounded-full", {
  variants: {
    tone: {
      neutral: "bg-muted-foreground",
      info: "bg-info",
      success: "bg-success",
      warning: "bg-warning",
      danger: "bg-destructive",
      brand: "bg-primary",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function StatusBadge({
  tone,
  children,
  pulse,
  className,
}: VariantProps<typeof statusVariants> & {
  children: React.ReactNode;
  /** Set for genuinely in-flight states only, so motion means "working". */
  pulse?: boolean;
  className?: string;
}): React.JSX.Element {
  return (
    <span className={cn(statusVariants({ tone }), className)}>
      <span
        className={cn(dotVariants({ tone }), pulse && "motion-safe:animate-pulse")}
        aria-hidden="true"
      />
      {children}
    </span>
  );
}

export { statusVariants };
