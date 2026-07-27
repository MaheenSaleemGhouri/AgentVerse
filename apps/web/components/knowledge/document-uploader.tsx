"use client";

import { AlertCircle, CheckCircle2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useDocumentUpload } from "@/lib/hooks/useDocumentUpload";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.txt,.md,.markdown,.csv,.tsv,.json";

export function DocumentUploader({
  workspaceId,
  knowledgeBaseId,
  onUploaded,
}: {
  workspaceId: string;
  knowledgeBaseId: string;
  onUploaded: () => void;
}): React.JSX.Element {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { uploads, isUploading, upload, dismiss, abortAll } = useDocumentUpload({
    workspaceId,
    knowledgeBaseId,
    onUploaded,
  });

  // Navigating away mid-upload must not leave a request hanging.
  useEffect(() => abortAll, [abortAll]);

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          void upload(Array.from(event.dataTransfer.files));
        }}
        className={cn(
          "flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center transition-colors",
          isDragging ? "border-primary bg-accent/60" : "border-border"
        )}
      >
        <span className="flex size-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Upload className="size-5" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-medium">Drag files here</p>
          <p className="text-sm text-muted-foreground">PDF, Word, Markdown, text, CSV or JSON</p>
        </div>
        {/* The button is the real control — drag-and-drop is an
            enhancement on top of it, never the only way in (Rule 7). */}
        <Button
          type="button"
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={isUploading}
        >
          {isUploading ? "Uploading…" : "Choose files"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          aria-label="Choose documents to upload"
          onChange={(event) => {
            void upload(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </div>

      {uploads.length > 0 && (
        <ul className="flex flex-col gap-2" aria-live="polite">
          {uploads.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {item.status === "done" && (
                    <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
                  )}
                  {item.status === "error" && (
                    <AlertCircle className="size-4 shrink-0 text-destructive" aria-hidden="true" />
                  )}
                  <span className="truncate text-sm font-medium">{item.filename}</span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {item.status === "uploading"
                      ? `${item.percent}%`
                      : item.status === "done"
                        ? "Queued for indexing"
                        : "Rejected"}
                  </span>
                </div>
                {item.status === "uploading" && (
                  <div
                    className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-label={`Uploading ${item.filename}`}
                    aria-valuenow={item.percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-200"
                      style={{ width: `${item.percent}%` }}
                    />
                  </div>
                )}
                {item.error && <p className="mt-1 text-xs text-destructive">{item.error}</p>}
              </div>
              {item.status !== "uploading" && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Dismiss ${item.filename}`}
                  onClick={() => dismiss(item.id)}
                >
                  <X className="size-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
