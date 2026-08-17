import { LifeBuoy } from "lucide-react";
import Link from "next/link";

import { listAgents } from "@/lib/api/agents";
import { listSupportTickets } from "@/lib/api/support-tickets";
import { formatRelativeTime } from "@/lib/format";

import { EmptyState } from "@/components/patterns/empty-state";
import { PageHeader } from "@/components/patterns/page-header";
import { CreateTicketDialog } from "@/components/support/create-ticket-dialog";
import { TicketStatusBadge } from "@/components/support/ticket-status-badge";
import { Card } from "@/components/ui/card";

export default async function SupportTicketsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const [tickets, agents] = await Promise.all([
    listSupportTickets(workspaceId),
    listAgents(workspaceId),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Support"
        description="File a ticket and an agent triages it — category, priority, and a draft reply."
        actions={<CreateTicketDialog workspaceId={workspaceId} agents={agents} />}
      />

      {tickets.length === 0 ? (
        <EmptyState
          icon={LifeBuoy}
          title="No tickets yet"
          description={
            agents.length === 0
              ? "Install or build an agent before filing a ticket — triage needs one to run."
              : "File one to see it triaged automatically."
          }
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {tickets.map((ticket) => (
            <li key={ticket.id}>
              <Link href={`/dashboard/${workspaceId}/support/${ticket.id}`}>
                <Card className="gap-1.5 p-4 transition-colors hover:bg-accent/50">
                  <div className="flex items-center gap-3">
                    <span className="font-medium">{ticket.subject}</span>
                    <TicketStatusBadge status={ticket.status} />
                    <time
                      dateTime={ticket.created_at}
                      className="ml-auto text-xs text-muted-foreground"
                    >
                      {formatRelativeTime(ticket.created_at)}
                    </time>
                  </div>
                  <p className="line-clamp-1 text-sm text-muted-foreground">{ticket.body}</p>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export const metadata = {
  title: "Support · AgentVerse",
};
