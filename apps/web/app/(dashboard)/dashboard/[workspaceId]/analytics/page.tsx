import { Activity, Bot, BookOpen, Users } from "lucide-react";

import { listAgents } from "@/lib/api/agents";
import { getReferrals } from "@/lib/api/billing";
import { getGrowthMetrics } from "@/lib/api/growth";
import { listKnowledgeBases } from "@/lib/api/knowledge";
import { listMembers } from "@/lib/api/workspaces";

import { GrowthSection } from "@/components/analytics/growth-section";
import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { StatCard } from "@/components/patterns/stat-card";

/**
 * Analytics.
 *
 * The composition counts below are real — they come from live API
 * responses. Everything time-series (run volume, success rate, latency
 * percentiles, cost over time) needs run history, which has no read
 * endpoint yet, so it is marked rather than filled with plausible-looking
 * invented curves.
 */
export default async function AnalyticsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const [agents, knowledgeBases, members, referrals, growthMetrics] = await Promise.all([
    listAgents(workspaceId),
    listKnowledgeBases(workspaceId),
    listMembers(workspaceId),
    getReferrals(workspaceId),
    getGrowthMetrics(workspaceId),
  ]);

  const published = agents.filter((agent) => agent.status === "active").length;
  const grounded = agents.length > 0 ? knowledgeBases.length > 0 : false;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Analytics"
        description="Run volume, success rate, latency, and cost attribution over time."
      />

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          Workspace composition — live
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Agents"
            value={agents.length}
            hint={`${published} published, ${agents.length - published} draft`}
            icon={Bot}
          />
          <StatCard
            label="Knowledge bases"
            value={knowledgeBases.length}
            hint={grounded ? "Grounding available" : "No grounding sources"}
            icon={BookOpen}
          />
          <StatCard label="Members" value={members.length} hint="With workspace access" icon={Users} />
          <StatCard
            label="Runs"
            value="—"
            hint="Needs the run read endpoint"
            icon={Activity}
          />
        </div>
      </section>

      <GrowthSection referrals={referrals} growthMetrics={growthMetrics} />

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Time series</h2>
        <IntegrationPending feature="analytics" />
      </section>
    </div>
  );
}

export const metadata = {
  title: "Analytics · AgentVerse",
};
