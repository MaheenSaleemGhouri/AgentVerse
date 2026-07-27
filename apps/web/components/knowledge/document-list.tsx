"use client";

import { FileText, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  deleteDocumentAction,
  listDocumentsAction,
  reindexDocumentAction,
} from "@/lib/api/actions";
import type { KbDocument } from "@/lib/api/knowledge";

import { DocumentStatusBadge } from "@/components/knowledge/document-status-badge";
import { Button } from "@/components/ui/button";

const POLL_INTERVAL_MS = 3000;

function isSettled(documents: KbDocument[]): boolean {
  return documents.every((d) => d.status === "indexed" || d.status === "failed");
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentList({
  workspaceId,
  knowledgeBaseId,
  initialDocuments,
  refreshToken,
}: {
  workspaceId: string;
  knowledgeBaseId: string;
  initialDocuments: KbDocument[];
  /** Bumped by the uploader after a batch lands, so a newly-queued
   * document appears without waiting for the next poll tick. */
  refreshToken: number;
}): React.JSX.Element {
  const [documents, setDocuments] = useState(initialDocuments);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocumentsAction(workspaceId, knowledgeBaseId));
    } catch {
      // A failed poll is not worth a toast — the next tick retries, and
      // the list on screen is still the last known-good state.
    }
  }, [workspaceId, knowledgeBaseId]);

  useEffect(() => {
    void refresh();
  }, [refreshToken, refresh]);

  useEffect(() => {
    // Polling stops once nothing is in flight: ingestion is the only
    // thing that changes a document out from under the user, so a page
    // of finished documents has nothing to poll for.
    if (isSettled(documents)) return;
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border py-12 text-center">
        <p className="font-medium">No documents yet</p>
        <p className="text-sm text-muted-foreground">
          Upload a file above — your agents can cite it as soon as it finishes indexing.
        </p>
      </div>
    );
  }

  async function onDelete(document: KbDocument): Promise<void> {
    try {
      await deleteDocumentAction(workspaceId, knowledgeBaseId, document.id);
      await refresh();
    } catch {
      toast.error(`Could not remove ${document.original_filename}.`);
    }
  }

  async function onReindex(document: KbDocument): Promise<void> {
    try {
      await reindexDocumentAction(workspaceId, knowledgeBaseId, document.id);
      await refresh();
      toast.success(`Reindexing ${document.original_filename}.`);
    } catch {
      toast.error(`Could not reindex ${document.original_filename}.`);
    }
  }

  return (
    <ul className="flex flex-col gap-2">
      {documents.map((document) => (
        <li
          key={document.id}
          className="flex items-center gap-3 rounded-lg border border-border px-4 py-3"
        >
          <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{document.original_filename}</p>
            <p className="text-xs text-muted-foreground">
              {formatSize(document.size_bytes)}
              {document.status === "indexed" && ` · ${document.chunk_count} chunks`}
            </p>
            {document.error_message && (
              <p className="mt-1 text-xs text-destructive">{document.error_message}</p>
            )}
          </div>
          <DocumentStatusBadge status={document.status} />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Reindex ${document.original_filename}`}
            onClick={() => void onReindex(document)}
          >
            <RefreshCw className="size-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Remove ${document.original_filename}`}
            onClick={() => void onDelete(document)}
          >
            <Trash2 className="size-4" />
          </Button>
        </li>
      ))}
    </ul>
  );
}
