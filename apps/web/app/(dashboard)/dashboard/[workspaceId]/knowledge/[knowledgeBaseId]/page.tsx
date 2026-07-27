import { notFound } from "next/navigation";

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
    const [knowledgeBase, documents] = await Promise.all([
      getKnowledgeBase(workspaceId, knowledgeBaseId),
      listDocuments(workspaceId, knowledgeBaseId),
    ]);
    return (
      <KnowledgeBaseDetail
        workspaceId={workspaceId}
        knowledgeBase={knowledgeBase}
        initialDocuments={documents}
      />
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }
}
