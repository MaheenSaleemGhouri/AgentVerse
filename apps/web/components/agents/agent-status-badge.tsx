import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground border-transparent",
  active: "bg-success-soft text-success-strong border-transparent",
  archived: "bg-destructive-soft text-destructive-strong border-transparent",
};

export function AgentStatusBadge({ status }: { status: string }): React.JSX.Element {
  return (
    <Badge
      variant="outline"
      className={cn("capitalize", STATUS_STYLES[status] ?? STATUS_STYLES.draft)}
    >
      {status}
    </Badge>
  );
}
