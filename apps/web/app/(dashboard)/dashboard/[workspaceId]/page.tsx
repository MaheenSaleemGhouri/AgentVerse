import { Bot, BookOpen, FileText, Users } from "lucide-react";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";

import { listAgents } from "@/lib/api/agents";
import { listKnowledgeBases } from "@/lib/api/knowledge";
import { listMembers, listMyWorkspaces } from "@/lib/api/workspaces";
import { auth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/format";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { QuickActions } from "@/components/dashboard/quick-actions";
import { EmptyState } from "@/components/patterns/empty-state";
import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { StatCard } from "@/components/patterns/stat-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/**
 * Workspace overview.
 *
 * Every number here is counted from a real API response — there is no
 * synthetic activity feed. The one panel without data (run history) says
 * so and names the endpoint it needs, rather than showing an invented
 * chart.
 */
export default async function DashboardPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const session = await auth.api.getSession({ headers: await headers() });

  const [workspaces, agents, knowledgeBases, members] = await Promise.all([
    listMyWorkspaces(),
    listAgents(workspaceId),
    listKnowledgeBases(workspaceId),
    listMembers(workspaceId),
  ]);

  const current = workspaces.find((workspace) => workspace.id === workspaceId);
  if (!current) notFound();

  const published = agents.filter((agent) => agent.status === "active").length;
  const recentAgents = [...agents]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .slice(0, 5);

  const firstName = session?.user.name?.split(" ")[0] ?? null;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title={firstName ? `${greeting()}, ${firstName}` : greeting()}
        description={`Here's where ${current.name} stands right now.`}
        actions={
          <Button asChild>
            <Link href={`/dashboard/${workspaceId}/agents`}>
              <Bot />
              New agent
            </Link>
          </Button>
        }
      />

      <section aria-label="Workspace statistics">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Agents"
            value={agents.length}
            hint={`${published} published`}
            icon={Bot}
          />
          <StatCard
            label="Knowledge bases"
            value={knowledgeBases.length}
            hint={knowledgeBases.length === 0 ? "None yet" : "Available for grounding"}
            icon={BookOpen}
          />
          <StatCard
            label="Team members"
            value={members.length}
            hint={`You are ${current.role}`}
            icon={Users}
          />
          <StatCard
            label="Your role"
            value={<span className="capitalize">{current.role}</span>}
            hint="Determines what you can change"
            icon={FileText}
          />
        </div>
      </section>

      <section aria-label="Quick actions" className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Quick actions</h2>
        <QuickActions workspaceId={workspaceId} />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section aria-label="Recent agents" className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">Recent agents</h2>
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/dashboard/${workspaceId}/agents`}>View all</Link>
            </Button>
          </div>

          {recentAgents.length === 0 ? (
            <EmptyState
              icon={Bot}
              title="No agents yet"
              description="Create your first agent to reach a working run in minutes."
              action={
                <Button asChild>
                  <Link href={`/dashboard/${workspaceId}/agents`}>Create an agent</Link>
                </Button>
              }
            />
          ) : (
            <Card className="gap-0 divide-y divide-border p-0">
              {recentAgents.map((agent) => (
                <Link
                  key={agent.id}
                  href={`/dashboard/${workspaceId}/agents/${agent.id}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-accent/40"
                >
                  <span
                    aria-hidden="true"
                    className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
                  >
                    <Bot className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{agent.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Updated {formatRelativeTime(agent.updated_at)}
                    </p>
                  </div>
                  <AgentStatusBadge status={agent.status} />
                </Link>
              ))}
            </Card>
          )}
        </section>

        <section aria-label="Knowledge bases" className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">Knowledge bases</h2>
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/dashboard/${workspaceId}/knowledge`}>View all</Link>
            </Button>
          </div>

          {knowledgeBases.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              title="No knowledge bases yet"
              description="Upload documents your agents can cite instead of guessing."
              action={
                <Button asChild>
                  <Link href={`/dashboard/${workspaceId}/knowledge`}>Create one</Link>
                </Button>
              }
            />
          ) : (
            <Card className="gap-0 divide-y divide-border p-0">
              {knowledgeBases.slice(0, 5).map((kb) => (
                <Link
                  key={kb.id}
                  href={`/dashboard/${workspaceId}/knowledge/${kb.id}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-accent/40"
                >
                  <span
                    aria-hidden="true"
                    className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
                  >
                    <BookOpen className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{kb.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {kb.description ?? kb.embedding_model}
                    </p>
                  </div>
                </Link>
              ))}
            </Card>
          )}
        </section>
      </div>

      <section aria-label="Recent activity" className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Run activity</h2>
        <IntegrationPending feature="runHistory" />
      </section>
    </div>
  );
}
