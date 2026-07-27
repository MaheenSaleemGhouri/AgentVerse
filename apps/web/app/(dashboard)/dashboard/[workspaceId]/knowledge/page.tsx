import { Library } from "lucide-react";
import Link from "next/link";

import { listKnowledgeBases } from "@/lib/api/knowledge";

import { CreateKnowledgeBaseDialog } from "@/components/knowledge/create-knowledge-base-dialog";

export default async function KnowledgePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const knowledgeBases = await listKnowledgeBases(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Knowledge</h1>
          <p className="text-sm text-muted-foreground">
            Give your agents documents to ground their answers in — and cite.
          </p>
        </div>
        <CreateKnowledgeBaseDialog workspaceId={workspaceId} />
      </div>

      {knowledgeBases.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
            <Library className="size-6" aria-hidden="true" />
          </span>
          <div>
            <p className="font-medium">No knowledge bases yet</p>
            <p className="text-sm text-muted-foreground">
              Create one, upload a document, then attach it to an agent.
            </p>
          </div>
          <CreateKnowledgeBaseDialog workspaceId={workspaceId} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {knowledgeBases.map((kb) => (
            <Link
              key={kb.id}
              href={`/dashboard/${workspaceId}/knowledge/${kb.id}`}
              className="flex flex-col gap-2 rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/40"
            >
              <span className="font-medium">{kb.name}</span>
              <span className="line-clamp-2 text-sm text-muted-foreground">
                {kb.description ?? "No description"}
              </span>
              <span className="mt-auto pt-2 text-xs text-muted-foreground">
                {kb.embedding_model}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
