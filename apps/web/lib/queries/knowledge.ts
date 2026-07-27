"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createKnowledgeBaseAction,
  deleteDocumentAction,
  deleteKnowledgeBaseAction,
  getKnowledgeBaseAction,
  listDocumentsAction,
  listKnowledgeBasesAction,
  reindexDocumentAction,
} from "@/lib/api/actions";
import type { KbDocument, KnowledgeBase } from "@/lib/api/knowledge";
import { queryKeys } from "@/lib/queries/keys";

export function useKnowledgeBases(workspaceId: string, initialData?: KnowledgeBase[]) {
  return useQuery({
    queryKey: queryKeys.knowledge.all(workspaceId),
    queryFn: () => listKnowledgeBasesAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useKnowledgeBase(workspaceId: string, knowledgeBaseId: string) {
  return useQuery({
    queryKey: queryKeys.knowledge.detail(workspaceId, knowledgeBaseId),
    queryFn: () => getKnowledgeBaseAction(workspaceId, knowledgeBaseId),
  });
}

/**
 * Documents poll while anything is still ingesting and stop once every
 * document has settled — chunking/embedding is the only thing that
 * changes a document out from under the user, so a fully-indexed list
 * has nothing to poll for.
 */
export function useDocuments(
  workspaceId: string,
  knowledgeBaseId: string,
  initialData?: KbDocument[]
) {
  return useQuery({
    queryKey: queryKeys.knowledge.documents(workspaceId, knowledgeBaseId),
    queryFn: () => listDocumentsAction(workspaceId, knowledgeBaseId),
    ...(initialData ? { initialData } : {}),
    refetchInterval: (query) => {
      const documents = query.state.data;
      if (!documents) return false;
      const settled = documents.every((d) => d.status === "indexed" || d.status === "failed");
      return settled ? false : 3000;
    },
  });
}

export function useCreateKnowledgeBase(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description: string | null }) =>
      createKnowledgeBaseAction(workspaceId, name, description),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all(workspaceId) });
    },
    onError: () => toast.error("Could not create the knowledge base — try again."),
  });
}

export function useDeleteKnowledgeBase(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (knowledgeBaseId: string) =>
      deleteKnowledgeBaseAction(workspaceId, knowledgeBaseId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all(workspaceId) });
    },
    onError: () => toast.error("Could not delete the knowledge base — try again."),
  });
}

export function useDeleteDocument(workspaceId: string, knowledgeBaseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      deleteDocumentAction(workspaceId, knowledgeBaseId, documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.documents(workspaceId, knowledgeBaseId),
      });
    },
    onError: () => toast.error("Could not remove the document — try again."),
  });
}

export function useReindexDocument(workspaceId: string, knowledgeBaseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      reindexDocumentAction(workspaceId, knowledgeBaseId, documentId),
    onSuccess: (document) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.knowledge.documents(workspaceId, knowledgeBaseId),
      });
      toast.success(`Reindexing ${document.original_filename}.`);
    },
    onError: () => toast.error("Could not reindex the document — try again."),
  });
}
