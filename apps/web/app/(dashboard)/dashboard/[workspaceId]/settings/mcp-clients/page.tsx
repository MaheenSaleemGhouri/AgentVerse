import { listMcpClients } from "@/lib/api/workspaces";

import { McpClientsPanel } from "@/components/settings/mcp-clients-panel";

export default async function McpClientsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const clients = await listMcpClients(workspaceId);

  return <McpClientsPanel workspaceId={workspaceId} initialClients={clients} />;
}

export const metadata = {
  title: "MCP clients · AgentVerse",
};
