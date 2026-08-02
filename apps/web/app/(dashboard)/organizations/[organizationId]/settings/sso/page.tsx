import { notFound } from "next/navigation";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import { getOrganization } from "@/lib/api/organizations";
import { listScimTokens } from "@/lib/api/scim-tokens";
import { listSsoConfigurations } from "@/lib/api/sso";
import { assertionConsumerServiceUrl, serviceProviderEntityId } from "@/lib/saml";
import { scimBaseUrl } from "@/lib/scim";

import { PageHeader } from "@/components/patterns/page-header";
import { ScimTokensPanel } from "@/components/organizations/scim-tokens-panel";
import { SsoConfigPanel } from "@/components/organizations/sso-config-panel";
import { Button } from "@/components/ui/button";

export default async function OrganizationSsoPage({
  params,
}: {
  params: Promise<{ organizationId: string }>;
}): Promise<React.JSX.Element> {
  const { organizationId } = await params;

  try {
    const [organization, configurations, scimTokens] = await Promise.all([
      getOrganization(organizationId),
      listSsoConfigurations(organizationId),
      listScimTokens(organizationId),
    ]);

    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="Single sign-on"
          description={`How members of ${organization.name} sign in. SSO is configured per organization — it does not change which workspaces anyone can reach.`}
          actions={
            <Button variant="outline" asChild>
              <Link href={`/organizations/${organizationId}/settings`}>Settings</Link>
            </Button>
          }
        />
        <SsoConfigPanel
          organizationId={organizationId}
          initialConfigurations={configurations}
          spEntityId={serviceProviderEntityId()}
          spAcsUrl={assertionConsumerServiceUrl(`saml-${organizationId}`)}
        />
        <ScimTokensPanel
          organizationId={organizationId}
          scimBaseUrl={scimBaseUrl()}
          initialTokens={scimTokens}
        />
      </div>
    );
  } catch (error) {
    // 403 = a member below org-admin; 404 = not a member at all. Both
    // are `notFound()` here rather than a crash — the page is simply not
    // theirs to see.
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
      notFound();
    }
    throw error;
  }
}

export const metadata = {
  title: "Single sign-on · AgentVerse",
};
