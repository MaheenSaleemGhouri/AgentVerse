import { BookOpen } from "lucide-react";
import Link from "next/link";

import { listDocuments, listKnowledgeBases, type KbDocument } from "@/lib/api/knowledge";

import { DocumentLibrary } from "@/components/knowledge/document-library";
import { EmptyState } from "@/components/patterns/empty-state";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

export interface LibraryRow {
  document: KbDocument;
  knowledgeBaseName: string;
}

/**
 * Every document across every knowledge base in one place.
 *
 * The API exposes documents per knowledge base only, so this fans out
 * one request per KB and joins the results. That is correct while a
 * workspace has a handful of KBs; if that count grows into the dozens
 * this wants a real cross-KB list endpoint rather than an N-request fan
 * out, and that is a backend change, not a frontend workaround.
 */
export default async function DocumentsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const knowledgeBases = await listKnowledgeBases(workspaceId);

  const perBase = await Promise.all(
    knowledgeBases.map(async (kb) => {
      const documents = await listDocuments(workspaceId, kb.id);
      return documents.map((document) => ({ document, knowledgeBaseName: kb.name }));
    })
  );
  const rows: LibraryRow[] = perBase.flat();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Document library"
        description="Every document across all knowledge bases, with its indexing status."
        actions={
          <Button asChild>
            <Link href={`/dashboard/${workspaceId}/upload`}>Upload documents</Link>
          </Button>
        }
      />

      {knowledgeBases.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="No knowledge bases yet"
          description="Documents live inside a knowledge base. Create one first, then upload."
          action={
            <Button asChild>
              <Link href={`/dashboard/${workspaceId}/knowledge`}>Create a knowledge base</Link>
            </Button>
          }
        />
      ) : (
        <DocumentLibrary workspaceId={workspaceId} rows={rows} />
      )}
    </div>
  );
}

export const metadata = {
  title: "Documents · AgentVerse",
};
