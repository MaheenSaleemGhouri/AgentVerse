import { notFound } from "next/navigation";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import { getOrganization, listOrgWorkspaces } from "@/lib/api/organizations";
import { listMyWorkspaces } from "@/lib/api/workspaces";

import { OrganizationSettingsPanel } from "@/components/organizations/organization-settings-panel";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

export default async function OrganizationSettingsPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}): Promise<React.JSX.Element> {
  const { organizationId } = await params;

  try {
    const [organization, attachedWorkspaces, myWorkspaces] = await Promise.all([
      getOrganization(organizationId),
      listOrgWorkspaces(organizationId),
      listMyWorkspaces(),
    ]);

    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title={organization.name}
          description={`/${organization.slug}`}
          actions={
            <div className="flex items-center gap-2">
              <Button variant="outline" asChild>
                <Link href={`/organizations/${organizationId}/settings/sso`}>Single sign-on</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link href={`/organizations/${organizationId}/members`}>Members</Link>
              </Button>
            </div>
          }
        />
        <OrganizationSettingsPanel
          organization={organization}
          initialAttachedWorkspaces={attachedWorkspaces}
          ownedWorkspaces={myWorkspaces.filter((workspace) => workspace.role === "owner")}
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
  title: "Organization settings · AgentVerse",
};
