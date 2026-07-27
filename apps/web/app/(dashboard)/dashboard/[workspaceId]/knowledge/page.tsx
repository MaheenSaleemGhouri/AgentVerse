import { listKnowledgeBases } from "@/lib/api/knowledge";

import { CreateKnowledgeBaseDialog } from "@/components/knowledge/create-knowledge-base-dialog";
import { KnowledgeBaseGrid } from "@/components/knowledge/knowledge-base-grid";
import { PageHeader } from "@/components/patterns/page-header";

export default async function KnowledgePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const knowledgeBases = await listKnowledgeBases(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Knowledge"
        description="Give your agents documents to ground their answers in — and cite."
        actions={<CreateKnowledgeBaseDialog workspaceId={workspaceId} />}
      />
      <KnowledgeBaseGrid workspaceId={workspaceId} initialKnowledgeBases={knowledgeBases} />
    </div>
  );
}

export const metadata = {
  title: "Knowledge · AgentVerse",
};
