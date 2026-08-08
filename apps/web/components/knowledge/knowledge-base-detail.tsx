"use client";

import { Bot, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { deleteKnowledgeBaseAction } from "@/lib/api/actions";
import type { Agent } from "@/lib/api/agents";
import type { KbDocument, KnowledgeBase } from "@/lib/api/knowledge";

import { DocumentList } from "@/components/knowledge/document-list";
import { DocumentUploader } from "@/components/knowledge/document-uploader";
import { SearchPreview } from "@/components/knowledge/search-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function KnowledgeBaseDetail({
  workspaceId,
  knowledgeBase,
  initialDocuments,
  linkedAgents,
}: {
  workspaceId: string;
  knowledgeBase: KnowledgeBase;
  initialDocuments: KbDocument[];
  /** Agents whose latest version attaches this knowledge base. Derived
   * server-side — there is no single endpoint for it. */
  linkedAgents: Agent[];
}): React.JSX.Element {
  const router = useRouter();
  const [refreshToken, setRefreshToken] = useState(0);
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function onDelete(): Promise<void> {
    try {
      await deleteKnowledgeBaseAction(workspaceId, knowledgeBase.id);
      router.push(`/dashboard/${workspaceId}/knowledge`);
    } catch {
      toast.error("Could not delete this knowledge base.");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{knowledgeBase.name}</h1>
          <p className="text-sm text-muted-foreground">
            {knowledgeBase.description ?? "No description"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Indexed with {knowledgeBase.embedding_model} (v
            {knowledgeBase.embedding_model_version})
          </p>

          {linkedAgents.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <Bot className="size-3.5" aria-hidden="true" />
                Used by
              </span>
              {linkedAgents.map((agent) => (
                <Link key={agent.id} href={`/dashboard/${workspaceId}/agents/${agent.id}`}>
                  <Badge variant="outline" className="hover:border-primary/50">
                    {agent.name}
                  </Badge>
                </Link>
              ))}
            </div>
          )}
        </div>
        {/* Confirmation friction scales with reversibility: deleting a
            knowledge base detaches it from every agent using it, so it
            asks rather than acting on one click (CLAUDE.md §15). */}
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger asChild>
            <Button variant="outline">
              <Trash2 />
              Delete
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete {knowledgeBase.name}?</DialogTitle>
              <DialogDescription>
                Its documents stop being searchable immediately.{" "}
                {linkedAgents.length > 0 ? (
                  <>
                    {linkedAgents.length} {linkedAgents.length === 1 ? "agent" : "agents"} —{" "}
                    {linkedAgents.map((agent) => agent.name).join(", ")} — will answer without
                    them.
                  </>
                ) : (
                  "No agent currently attaches it."
                )}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={() => void onDelete()}>
                Delete knowledge base
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Tabs defaultValue="documents">
        <TabsList>
          <TabsTrigger value="documents">Documents</TabsTrigger>
          <TabsTrigger value="test">Test retrieval</TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="mt-4 flex flex-col gap-4">
          <DocumentUploader
            workspaceId={workspaceId}
            knowledgeBaseId={knowledgeBase.id}
            onUploaded={() => setRefreshToken((n) => n + 1)}
          />
          <DocumentList
            workspaceId={workspaceId}
            knowledgeBaseId={knowledgeBase.id}
            initialDocuments={initialDocuments}
            refreshToken={refreshToken}
          />
        </TabsContent>

        <TabsContent value="test" className="mt-4">
          <SearchPreview workspaceId={workspaceId} knowledgeBaseId={knowledgeBase.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
