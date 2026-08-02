import { listMyOrganizations } from "@/lib/api/organizations";

import { OrganizationsList } from "@/components/organizations/organizations-list";
import { PageHeader } from "@/components/patterns/page-header";

export default async function OrganizationsPage(): Promise<React.JSX.Element> {
  const organizations = await listMyOrganizations();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Organizations"
        description="Group workspaces for shared billing, SSO, and branding. Attaching a workspace never grants access to it — workspace membership is unchanged."
      />
      <OrganizationsList initialOrganizations={organizations} />
    </div>
  );
}

export const metadata = {
  title: "Organizations · AgentVerse",
};
