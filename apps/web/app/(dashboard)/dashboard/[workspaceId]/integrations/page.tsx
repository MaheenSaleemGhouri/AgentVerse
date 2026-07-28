import { listCatalog, listInstalled } from "@/lib/api/integrations";

import { ConnectionsList } from "@/components/integrations/connections-list";
import { Marketplace } from "@/components/integrations/marketplace";
import { PageHeader } from "@/components/patterns/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default async function IntegrationsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  // Both server-fetched for first paint and passed as initial data, so
  // the marketplace and the connections list are complete on load rather
  // than flashing skeletons for data the page already had.
  const [catalog, installed] = await Promise.all([
    listCatalog(workspaceId),
    listInstalled(workspaceId),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Integrations"
        description="Connect external services through MCP and give your agents their tools."
      />

      {/* Opens on Connected when there is something to see, and on the
          marketplace when there is not — a first-time user should land on
          the thing they can act on. */}
      <Tabs defaultValue={installed.length > 0 ? "connected" : "marketplace"}>
        <TabsList>
          <TabsTrigger value="connected">
            Connected{installed.length > 0 ? ` (${installed.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="marketplace">Marketplace</TabsTrigger>
        </TabsList>

        <TabsContent value="connected" className="mt-5">
          <ConnectionsList workspaceId={workspaceId} initialServers={installed} />
        </TabsContent>

        <TabsContent value="marketplace" className="mt-5">
          <Marketplace
            workspaceId={workspaceId}
            initialCatalog={catalog}
            initialInstalled={installed}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export const metadata = {
  title: "Integrations · AgentVerse",
};
