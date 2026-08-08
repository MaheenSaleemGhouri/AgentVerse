import { Activity, BookOpen, Bot, CircleDollarSign, Users2 } from "lucide-react";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";

import { listAgents } from "@/lib/api/agents";
import { getEntitlements, getInvoicePreview } from "@/lib/api/billing";
import { listAuditLogs } from "@/lib/api/audit-logs";
import { listKnowledgeBases } from "@/lib/api/knowledge";
import { listTeams } from "@/lib/api/teams";
import { listMembers, listMyWorkspaces } from "@/lib/api/workspaces";
import { auth } from "@/lib/auth";
import { formatCents, formatNumber, formatRelativeTime } from "@/lib/format";
import { ROLE_ORDER } from "@/lib/roles";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { QuickActions } from "@/components/dashboard/quick-actions";
import { UsageOverview } from "@/components/dashboard/usage-overview";
import { WelcomeBanner } from "@/components/dashboard/welcome-banner";
import { EmptyState } from "@/components/patterns/empty-state";
import { IntegrationPending } from "@/components/patterns/integration-pending";
import { StatCard } from "@/components/patterns/stat-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

function greeting(name: string | null): string {
  const hour = new Date().getHours();
  const time = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  return name ? `${time}, ${name}` : time;
}

/**
 * Workspace overview.
 *
 * Every number on this page is counted from a real API response. The
 * approved reference (panel 05) shows four stat cards with
 * month-over-month deltas and a six-month executions chart; two of those
 * are not things this backend can answer:
 *
 *   - **Success rate** needs run outcomes, and runs have no read path
 *     (`feature-availability.ts` → `runHistory`).
 *   - **Deltas and the monthly series** need a previous-period
 *     comparison. Usage is metered against the *current* billing period
 *     only.
 *
 * So this page shows what the data supports — real runs metered this
 * period, real cost in integer cents, real usage against real
 * allowances — and names the missing endpoint where the reference's
 * fourth card would go. A dashboard with an invented success rate is
 * worse than one that says what it is waiting for.
 */
export default async function DashboardPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const session = await auth.api.getSession({ headers: await headers() });

  const [workspaces, agents, knowledgeBases, members, teams] = await Promise.all([
    listMyWorkspaces(),
    listAgents(workspaceId),
    listKnowledgeBases(workspaceId),
    listMembers(workspaceId),
    listTeams(workspaceId),
  ]);

  const current = workspaces.find((workspace) => workspace.id === workspaceId);
  if (!current) notFound();

  // Billing and audit are role-gated, and the dashboard must render for
  // every role. Fetched separately from the block above so one 403 for a
  // viewer cannot take the whole page down with it.
  const canReadBilling = ROLE_ORDER[current.role] >= ROLE_ORDER.admin;
  const canReadAudit = ROLE_ORDER[current.role] >= ROLE_ORDER.analyst;

  const [entitlements, invoice, auditPage] = await Promise.all([
    canReadBilling ? getEntitlements(workspaceId).catch(() => null) : Promise.resolve(null),
    canReadBilling ? getInvoicePreview(workspaceId).catch(() => null) : Promise.resolve(null),
    canReadAudit
      ? listAuditLogs(workspaceId, { limit: 6 }).catch(() => null)
      : Promise.resolve(null),
  ]);

  const runsThisPeriod = entitlements?.metered.find((line) => line.dimension === "agent_runs");
  const published = agents.filter((agent) => agent.status === "active").length;
  const recentAgents = [...agents]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .slice(0, 5);

  const firstName = session?.user.name?.split(" ")[0] ?? null;

  const status =
    agents.length === 0
      ? "No agents yet — the fastest way in is to install a template and edit it."
      : runsThisPeriod && runsThisPeriod.used > 0
        ? `${formatNumber(runsThisPeriod.used)} ${runsThisPeriod.used === 1 ? "run" : "runs"} this billing period.`
        : `${agents.length} ${agents.length === 1 ? "agent" : "agents"} configured, nothing run yet this period.`;

  return (
    <div className="flex flex-col gap-8">
      <WelcomeBanner
        greeting={greeting(firstName)}
        workspaceName={current.name}
        status={status}
      />

      <section aria-label="Workspace statistics">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Agents"
            value={formatNumber(agents.length)}
            hint={`${formatNumber(published)} published`}
            icon={Bot}
          />
          <StatCard
            label="Runs this period"
            value={runsThisPeriod ? formatNumber(runsThisPeriod.used) : "—"}
            hint={
              runsThisPeriod
                ? runsThisPeriod.limit === null
                  ? "Unlimited on this plan"
                  : `of ${formatNumber(runsThisPeriod.limit)} included`
                : "Visible to admins and owners"
            }
            icon={Activity}
          />
          <StatCard
            label="Cost this period"
            // `subtotal_cents`, not a total: the draft invoice is the
            // plan fee plus accrued overage before tax, and calling it a
            // total would overstate what the API actually computed.
            value={invoice ? formatCents(invoice.subtotal_cents, invoice.currency) : "—"}
            hint={invoice ? "Accrued so far, before tax" : "Visible to admins and owners"}
            icon={CircleDollarSign}
          />
          <StatCard
            label="Knowledge & teams"
            value={formatNumber(knowledgeBases.length + teams.length)}
            hint={`${formatNumber(knowledgeBases.length)} knowledge · ${formatNumber(teams.length)} teams`}
            icon={BookOpen}
          />
        </div>
      </section>

      <section aria-label="Quick actions" className="space-y-3">
        <h2 className="font-display text-base font-semibold tracking-tight">Quick actions</h2>
        <QuickActions workspaceId={workspaceId} />
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section aria-label="Agents" className="space-y-3 xl:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-base font-semibold tracking-tight">Your agents</h2>
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/dashboard/${workspaceId}/agents`}>View all</Link>
            </Button>
          </div>

          {recentAgents.length === 0 ? (
            <EmptyState
              icon={Bot}
              title="No agents yet"
              description="An agent is instructions, a model, and optionally tools and knowledge. Installing a template and editing it is faster than starting from a blank prompt."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button asChild>
                    <Link href={`/dashboard/${workspaceId}/marketplace`}>Browse templates</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link href={`/dashboard/${workspaceId}/agents`}>Start from scratch</Link>
                  </Button>
                </div>
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
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
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

        <section aria-label="Usage" className="space-y-3">
          <h2 className="sr-only">Usage</h2>
          {entitlements ? (
            <UsageOverview metered={entitlements.metered} plan={entitlements.plan} />
          ) : (
            <Card className="gap-2 p-6">
              <h3 className="font-display text-base font-semibold tracking-tight">
                Usage this period
              </h3>
              <p className="text-sm text-muted-foreground">
                Plan usage and cost are visible to admins and owners.
              </p>
            </Card>
          )}
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section aria-label="Recent activity" className="xl:col-span-2">
          <ActivityFeed
            workspaceId={workspaceId}
            entries={auditPage?.data ?? []}
            canRead={auditPage !== null}
          />
        </section>

        <section aria-label="Run history" className="space-y-3">
          <h2 className="sr-only">Run history</h2>
          <IntegrationPending feature="runHistory" />
        </section>
      </div>

      <section aria-label="Teams" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-base font-semibold tracking-tight">AI teams</h2>
          <Button variant="ghost" size="sm" asChild>
            <Link href={`/dashboard/${workspaceId}/teams`}>View all</Link>
          </Button>
        </div>
        {teams.length === 0 ? (
          <EmptyState
            icon={Users2}
            title="No teams yet"
            description="A team lets several agents hand work to each other — a supervisor delegating to specialists, or a planner, executor and critic."
            action={
              <Button variant="outline" asChild>
                <Link href={`/dashboard/${workspaceId}/teams`}>Create a team</Link>
              </Button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {teams.slice(0, 3).map((team) => (
              <Card key={team.id} className="gap-1 p-5">
                <Link
                  href={`/dashboard/${workspaceId}/teams/${team.id}`}
                  className="font-medium hover:underline"
                >
                  {team.name}
                </Link>
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {team.description ?? `${team.topology.replace(/_/g, " ")} topology`}
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>

      <p className="text-xs text-muted-foreground">
        You are {current.role} in {current.name} · {formatNumber(members.length)}{" "}
        {members.length === 1 ? "member" : "members"}
      </p>
    </div>
  );
}
