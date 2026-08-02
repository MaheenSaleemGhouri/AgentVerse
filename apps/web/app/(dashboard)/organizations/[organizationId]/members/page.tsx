import { notFound } from "next/navigation";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import { getOrganization, listOrgMembers } from "@/lib/api/organizations";
import { ROLE_ORDER } from "@/lib/roles";

import { InviteMemberDialog } from "@/components/team/invite-member-dialog";
import { MembersTable } from "@/components/team/members-table";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

export default async function OrganizationMembersPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}): Promise<React.JSX.Element> {
  const { organizationId } = await params;

  try {
    const [organization, members] = await Promise.all([
      getOrganization(organizationId),
      listOrgMembers(organizationId),
    ]);
    const canManage = ROLE_ORDER[organization.role] >= ROLE_ORDER.admin;
    const scope = { type: "organization" as const, id: organizationId };

    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title={`${organization.name} members`}
          description="Organization membership — independent of any workspace's own members (ADR-0006)."
          actions={
            <div className="flex items-center gap-2">
              {canManage && <InviteMemberDialog scope={scope} />}
              <Button variant="outline" asChild>
                <Link href={`/organizations/${organizationId}/settings`}>Settings</Link>
              </Button>
            </div>
          }
        />
        <MembersTable
          scope={scope}
          initialMembers={members}
          viewerRole={organization.role}
          canManage={canManage}
        />
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
  title: "Organization members · AgentVerse",
};
