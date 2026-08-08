import { notFound } from "next/navigation";

import { listAgents, getLatestVersion } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import { getKnowledgeBase, listDocuments } from "@/lib/api/knowledge";

import { KnowledgeBaseDetail } from "@/components/knowledge/knowledge-base-detail";

export default async function KnowledgeBasePage({
  params,
}: {
  params: Promise<{ workspaceId: string; knowledgeBaseId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId, knowledgeBaseId } = await params;

  try {
    const [knowledgeBase, documents, agents] = await Promise.all([
      getKnowledgeBase(workspaceId, knowledgeBaseId),
      listDocuments(workspaceId, knowledgeBaseId),
      listAgents(workspaceId),
    ]);

    // "Which agents use this?" is nowhere in the API as a single call —
    // `knowledge_base_ids` lives on the agent's *version*, not the KB —
    // so it is derived by checking every agent's latest version. Fetched
    // in parallel and bounded by this workspace's agent count, which is
    // small; this is a detail page loaded once, not a polled surface.
    const versions = await Promise.all(
      agents.map((agent) =>
        getLatestVersion(workspaceId, agent.id).catch(() => null)
      )
    );
    const linkedAgents = agents.filter((_agent, index) =>
      versions[index]?.knowledge_base_ids.includes(knowledgeBaseId)
    );

    return (
      <KnowledgeBaseDetail
        workspaceId={workspaceId}
        knowledgeBase={knowledgeBase}
        initialDocuments={documents}
        linkedAgents={linkedAgents}
      />
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}
