import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { getOrganizationDashboard } from "@/lib/api/organizations";

import { MemberPresenceTable } from "@/components/organizations/member-presence-table";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

function Stat({ label, value }: { label: string; value: number }): React.JSX.Element {
  return (
    <Card className="gap-1 p-4">
      <span className="text-2xl font-semibold tabular-nums">{value.toLocaleString()}</span>
      <span className="text-sm text-muted-foreground">{label}</span>
    </Card>
  );
}

/**
 * The organization's overview: how big it is, who is in it, and when
 * they were last active.
 *
 * Deliberately shows nothing workspace-scoped. Organization membership
 * grants no workspace access (ADR-0011), so this page must not become a
 * side channel into workspaces the caller is not a member of — it
 * reports the count of attached workspaces, never their contents.
 */
export default async function OrganizationDashboardPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}): Promise<React.JSX.Element> {
  const { organizationId } = await params;

  try {
    const { organization, stats, members } = await getOrganizationDashboard(organizationId);

    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title={organization.name}
          description={`/${organization.slug}`}
          actions={
            <div className="flex items-center gap-2">
              <Button variant="outline" asChild>
                <Link href={`/organizations/${organizationId}/members`}>Members</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link href={`/organizations/${organizationId}/settings`}>Settings</Link>
              </Button>
            </div>
          }
        />

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Workspaces" value={stats.workspace_count} />
          <Stat label="Members" value={stats.member_count} />
          <Stat label="Active members" value={stats.active_member_count} />
          <Stat label="Suspended" value={stats.suspended_member_count} />
        </div>

        <Card className="gap-4 p-6">
          <div>
            <h2 className="font-medium">Members</h2>
            <p className="text-sm text-muted-foreground">
              &ldquo;Signed in&rdquo; means the member holds an unexpired session — it is not a
              live presence indicator.
            </p>
          </div>
          <MemberPresenceTable members={members} />
        </Card>
      </div>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}

export const metadata = {
  title: "Organization · AgentVerse",
};
