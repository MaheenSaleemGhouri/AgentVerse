import { LifeBuoy } from "lucide-react";
import { notFound } from "next/navigation";
import * as React from "react";

import { ApiError } from "@/lib/api/client";
import { getSupportTicket } from "@/lib/api/support-tickets";
import { formatRelativeTime } from "@/lib/format";

import { ResolveTicketButton } from "@/components/support/resolve-ticket-button";
import { TicketStatusBadge } from "@/components/support/ticket-status-badge";
import { TriageResultCard } from "@/components/support/triage-result-card";
import { Card } from "@/components/ui/card";

interface PageProps {
  params: Promise<{ workspaceId: string; ticketId: string }>;
}

export default async function SupportTicketDetailPage({
  params,
}: PageProps): Promise<React.JSX.Element> {
  const { workspaceId, ticketId } = await params;

  const ticket = await getSupportTicket(workspaceId, ticketId).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <span
          aria-hidden="true"
          className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground"
        >
          <LifeBuoy className="size-6" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{ticket.subject}</h1>
            <TicketStatusBadge status={ticket.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Filed {formatRelativeTime(ticket.created_at)}
          </p>
        </div>

        {ticket.status !== "resolved" && (
          <ResolveTicketButton workspaceId={workspaceId} ticketId={ticket.id} />
        )}
      </div>

      <Card className="p-6">
        <p className="mb-1 text-sm font-medium text-muted-foreground">Original message</p>
        <p className="text-sm whitespace-pre-wrap">{ticket.body}</p>
      </Card>

      <TriageResultCard ticket={ticket} />
    </div>
  );
}

export async function generateMetadata({ params }: PageProps): Promise<{ title: string }> {
  const { workspaceId, ticketId } = await params;
  const ticket = await getSupportTicket(workspaceId, ticketId).catch(() => null);
  return { title: ticket ? `${ticket.subject} · Support` : "Support · AgentVerse" };
}
