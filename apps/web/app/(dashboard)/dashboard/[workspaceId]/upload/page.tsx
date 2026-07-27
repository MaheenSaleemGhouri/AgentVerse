import { BookOpen } from "lucide-react";
import Link from "next/link";

import { listKnowledgeBases } from "@/lib/api/knowledge";

import { UploadCenter } from "@/components/knowledge/upload-center";
import { EmptyState } from "@/components/patterns/empty-state";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

export default async function UploadPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const knowledgeBases = await listKnowledgeBases(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Upload center"
        description="Add documents to a knowledge base. Indexing runs in the background — you can leave this page once uploads finish."
      />

      {knowledgeBases.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="Create a knowledge base first"
          description="Documents belong to a knowledge base, which pins the embedding model used to index them."
          action={
            <Button asChild>
              <Link href={`/dashboard/${workspaceId}/knowledge`}>Create a knowledge base</Link>
            </Button>
          }
        />
      ) : (
        <UploadCenter workspaceId={workspaceId} knowledgeBases={knowledgeBases} />
      )}
    </div>
  );
}

export const metadata = {
  title: "Upload · AgentVerse",
};
