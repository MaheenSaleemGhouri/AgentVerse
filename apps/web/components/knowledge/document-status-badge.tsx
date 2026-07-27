import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Status is never colour alone — each state carries an icon and a text
 * label (CLAUDE.md §15, Rule 7).
 */
interface StatusStyle {
  label: string;
  className: string;
  Icon: React.ComponentType<{ className?: string }>;
}

/** Also the fallback for an unrecognised status — a future backend state
 * renders as "Queued" rather than crashing the list. */
const PENDING: StatusStyle = {
  label: "Queued",
  className: "bg-muted text-muted-foreground border-transparent",
  Icon: Clock,
};

const STATUS: Record<string, StatusStyle> = {
  pending: PENDING,
  processing: {
    label: "Indexing",
    className: "bg-warning-soft text-warning border-transparent",
    Icon: Loader2,
  },
  indexed: {
    label: "Indexed",
    className: "bg-success-soft text-success border-transparent",
    Icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    className: "bg-destructive-soft text-destructive border-transparent",
    Icon: AlertCircle,
  },
};

export function DocumentStatusBadge({ status }: { status: string }): React.JSX.Element {
  const entry = STATUS[status] ?? PENDING;
  const Icon = entry.Icon;
  return (
    <Badge variant="outline" className={cn("gap-1.5", entry.className)}>
      <Icon
        className={cn("size-3", status === "processing" && "motion-safe:animate-spin")}
        aria-hidden="true"
      />
      {entry.label}
    </Badge>
  );
}
