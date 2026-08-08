import Link from "next/link";
import * as React from "react";

import { env } from "@/lib/env";

import { ApiExplorer } from "@/components/api-explorer/api-explorer";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

/**
 * The interactive API explorer.
 *
 * Under Settings rather than as a top-level section: it sits next to API
 * keys, which is where someone already is when they are about to
 * integrate. The docs portal links here for the same reason — reading
 * about an endpoint and trying it should be one step apart.
 */
export default async function ApiExplorerPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  // The URL a *customer* would call, not the internal one this server
  // uses. Printing `apiInternalUrl` in a snippet would hand someone a
  // host that only resolves inside our network.
  const publicBaseUrl = env.apiPublicUrl ?? "https://api.agentverse.dev";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="API explorer"
        description="Try a request against your own workspace, see the real response, and copy the code to call it yourself."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild>
              <Link href={`/dashboard/${workspaceId}/settings/api-keys`}>API keys</Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/docs/platform/api-keys-and-sdks">Docs</Link>
            </Button>
          </div>
        }
      />
      <ApiExplorer workspaceId={workspaceId} publicBaseUrl={publicBaseUrl} />
    </div>
  );
}

export const metadata = {
  title: "API explorer · AgentVerse",
};
