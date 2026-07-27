import { listApiKeys } from "@/lib/api/workspaces";

import { ApiKeysPanel } from "@/components/settings/api-keys-panel";

export default async function ApiKeysPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const keys = await listApiKeys(workspaceId);

  return <ApiKeysPanel workspaceId={workspaceId} initialKeys={keys} />;
}

export const metadata = {
  title: "API keys · AgentVerse",
};
