"use client";

import { useCallback, useRef, useState } from "react";

export interface UploadItem {
  /** Stable across the upload's lifetime — the filename is not unique. */
  id: string;
  filename: string;
  /** 0–100. Real bytes-sent progress, not a simulated animation. */
  percent: number;
  status: "uploading" | "done" | "error";
  error?: string;
}

/**
 * Uploads files one at a time via `XMLHttpRequest`, which is used here
 * (rather than `fetch`) for one reason: it is the only browser API that
 * reports request-body upload progress. Serial rather than parallel so
 * a batch of large files can't saturate the connection and make every
 * individual bar crawl at once.
 *
 * In-flight requests are aborted on unmount by the caller so navigating
 * away doesn't leak a connection (CLAUDE.md §6).
 */
export function useDocumentUpload({
  workspaceId,
  knowledgeBaseId,
  onUploaded,
}: {
  workspaceId: string;
  knowledgeBaseId: string;
  onUploaded: () => void;
}): {
  uploads: UploadItem[];
  isUploading: boolean;
  upload: (files: File[]) => Promise<void>;
  dismiss: (id: string) => void;
  abortAll: () => void;
} {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const inFlight = useRef<Set<XMLHttpRequest>>(new Set());

  const patch = useCallback((id: string, changes: Partial<UploadItem>) => {
    setUploads((current) => current.map((u) => (u.id === id ? { ...u, ...changes } : u)));
  }, []);

  const uploadOne = useCallback(
    (item: UploadItem, file: File) =>
      new Promise<void>((resolve) => {
        const request = new XMLHttpRequest();
        inFlight.current.add(request);
        const body = new FormData();
        body.append("file", file);

        request.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            patch(item.id, { percent: Math.round((event.loaded / event.total) * 100) });
          }
        });

        request.addEventListener("loadend", () => {
          inFlight.current.delete(request);
          if (request.status === 202) {
            patch(item.id, { percent: 100, status: "done" });
          } else {
            patch(item.id, { status: "error", error: readError(request) });
          }
          resolve();
        });

        request.open(
          "POST",
          `/api/knowledge/${knowledgeBaseId}/documents?workspaceId=${encodeURIComponent(workspaceId)}`
        );
        request.send(body);
      }),
    [knowledgeBaseId, workspaceId, patch]
  );

  const upload = useCallback(
    async (files: File[]): Promise<void> => {
      if (files.length === 0) return;
      const items: UploadItem[] = files.map((file) => ({
        id: `${file.name}-${file.size}-${crypto.randomUUID()}`,
        filename: file.name,
        percent: 0,
        status: "uploading",
      }));
      setUploads((current) => [...current, ...items]);
      setIsUploading(true);
      try {
        for (const [index, file] of files.entries()) {
          await uploadOne(items[index]!, file);
        }
      } finally {
        setIsUploading(false);
        onUploaded();
      }
    },
    [uploadOne, onUploaded]
  );

  const dismiss = useCallback((id: string) => {
    setUploads((current) => current.filter((u) => u.id !== id));
  }, []);

  const abortAll = useCallback(() => {
    for (const request of inFlight.current) request.abort();
    inFlight.current.clear();
  }, []);

  return { uploads, isUploading, upload, dismiss, abortAll };
}

/**
 * apps/api returns `{"detail": "..."}` with a user-safe rejection reason
 * (wrong file type, too large, empty). Surfacing it verbatim is the
 * point — "Something went wrong" would leave the user with no idea which
 * file to fix (`ux-designer`).
 */
function readError(request: XMLHttpRequest): string {
  try {
    const parsed: unknown = JSON.parse(request.responseText);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "detail" in parsed &&
      typeof (parsed as { detail: unknown }).detail === "string"
    ) {
      return (parsed as { detail: string }).detail;
    }
  } catch {
    // Non-JSON body (a proxy error page, say) — fall through.
  }
  return request.status === 0 ? "Upload was interrupted." : "Upload failed. Try again.";
}
