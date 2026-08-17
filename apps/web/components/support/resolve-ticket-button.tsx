"use client";

import { CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useResolveSupportTicket } from "@/lib/queries/support-tickets";

import { Button } from "@/components/ui/button";

export function ResolveTicketButton({
  workspaceId,
  ticketId,
}: {
  workspaceId: string;
  ticketId: string;
}): React.JSX.Element {
  const router = useRouter();
  const resolve = useResolveSupportTicket(workspaceId);

  async function handleResolve(): Promise<void> {
    try {
      await resolve.mutateAsync(ticketId);
      router.refresh();
    } catch {
      toast.error("Could not resolve this ticket — try again.");
    }
  }

  return (
    <Button variant="outline" onClick={() => void handleResolve()} disabled={resolve.isPending}>
      <CheckCircle2 className="size-4" aria-hidden="true" />
      {resolve.isPending ? "Resolving…" : "Mark resolved"}
    </Button>
  );
}
