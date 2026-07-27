import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type KnowledgeBase = components["schemas"]["KnowledgeBaseResponse"];
export type KbDocument = components["schemas"]["KbDocumentResponse"];
export type SearchResponse = components["schemas"]["SearchResponse"];
export type SearchHit = components["schemas"]["SearchHitResponse"];

function base(workspaceId: string): string {
  return `/api/v1/workspaces/${workspaceId}/knowledge-bases`;
}

export async function listKnowledgeBases(workspaceId: string): Promise<KnowledgeBase[]> {
  return apiFetch<KnowledgeBase[]>(base(workspaceId));
}

export async function getKnowledgeBase(
  workspaceId: string,
  knowledgeBaseId: string
): Promise<KnowledgeBase> {
  return apiFetch<KnowledgeBase>(`${base(workspaceId)}/${knowledgeBaseId}`);
}

export async function createKnowledgeBase(
  workspaceId: string,
  body: components["schemas"]["CreateKnowledgeBaseRequest"]
): Promise<KnowledgeBase> {
  return apiFetch<KnowledgeBase>(base(workspaceId), {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteKnowledgeBase(
  workspaceId: string,
  knowledgeBaseId: string
): Promise<void> {
  await apiFetch<void>(`${base(workspaceId)}/${knowledgeBaseId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function listDocuments(
  workspaceId: string,
  knowledgeBaseId: string
): Promise<KbDocument[]> {
  return apiFetch<KbDocument[]>(`${base(workspaceId)}/${knowledgeBaseId}/documents`);
}

export async function deleteDocument(
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string
): Promise<void> {
  await apiFetch<void>(`${base(workspaceId)}/${knowledgeBaseId}/documents/${documentId}`, {
    method: "DELETE",
    skipJson: true,
  });
}

export async function reindexDocument(
  workspaceId: string,
  knowledgeBaseId: string,
  documentId: string
): Promise<KbDocument> {
  return apiFetch<KbDocument>(
    `${base(workspaceId)}/${knowledgeBaseId}/documents/${documentId}/reindex`,
    { method: "POST" }
  );
}

export async function searchKnowledgeBase(
  workspaceId: string,
  knowledgeBaseId: string,
  query: string
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(`${base(workspaceId)}/${knowledgeBaseId}/search`, {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}
