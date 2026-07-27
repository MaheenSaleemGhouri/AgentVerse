import { ArrowRight, KeyRound, Plug } from "lucide-react";
import Link from "next/link";

import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { Card } from "@/components/ui/card";

/**
 * Third-party integrations.
 *
 * No provider tiles are listed: naming services AgentVerse does not yet
 * connect to would read as a supported-integrations list, which would be
 * a false claim. What *is* real today — API keys for calling AgentVerse
 * from elsewhere — is linked, because that is the integration path that
 * actually works right now.
 */
export default async function IntegrationsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Integrations"
        description="Authorise a service once per workspace and reuse it across agents."
      />

      <Card className="gap-3 p-6">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
          >
            <KeyRound className="size-4.5" />
          </span>
          <div className="min-w-0">
            <p className="font-medium">Available now — API access</p>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Integrating <em>into</em> AgentVerse works today: issue a workspace-scoped API key and
              call the agent, knowledge, and run endpoints from your own systems.
            </p>
            <Link
              href={`/dashboard/${workspaceId}/settings/api-keys`}
              className="mt-2 inline-flex items-center gap-1 text-sm text-primary underline underline-offset-4"
            >
              Manage API keys
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Plug className="size-4" aria-hidden="true" />
          Outbound integrations
        </h2>
        <IntegrationPending feature="integrations" />
      </div>
    </div>
  );
}

export const metadata = {
  title: "Integrations · AgentVerse",
};
