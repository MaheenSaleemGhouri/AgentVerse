"use client";

import { ArrowRight, FileCheck2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { KnowledgeBase } from "@/lib/api/knowledge";

import { DocumentUploader } from "@/components/knowledge/document-uploader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ACCEPTED = [
  { label: "PDF", detail: ".pdf" },
  { label: "Word", detail: ".docx" },
  { label: "Markdown", detail: ".md" },
  { label: "Text", detail: ".txt" },
  { label: "CSV", detail: ".csv" },
  { label: "JSON", detail: ".json" },
];

export function UploadCenter({
  workspaceId,
  knowledgeBases,
}: {
  workspaceId: string;
  knowledgeBases: KnowledgeBase[];
}): React.JSX.Element {
  const [targetId, setTargetId] = React.useState(knowledgeBases[0]?.id ?? "");
  const [uploadedCount, setUploadedCount] = React.useState(0);

  const target = knowledgeBases.find((kb) => kb.id === targetId) ?? null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="space-y-4">
        <Card className="gap-4 p-5">
          <div className="space-y-2">
            <Label htmlFor="target-kb">Destination knowledge base</Label>
            <Select value={targetId} onValueChange={setTargetId}>
              <SelectTrigger id="target-kb" className="w-full sm:w-96">
                <SelectValue placeholder="Choose a knowledge base" />
              </SelectTrigger>
              <SelectContent>
                {knowledgeBases.map((kb) => (
                  <SelectItem key={kb.id} value={kb.id}>
                    {kb.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {target && (
              <p className="text-xs text-muted-foreground">
                Indexed with{" "}
                <span className="font-mono">
                  {target.embedding_model} v{target.embedding_model_version}
                </span>
                . A knowledge base is searched with the model it was built with.
              </p>
            )}
          </div>

          {targetId && (
            <DocumentUploader
              // Remounting per destination clears the previous target's
              // upload list, so a finished batch can't look like it
              // belongs to the newly selected knowledge base.
              key={targetId}
              workspaceId={workspaceId}
              knowledgeBaseId={targetId}
              onUploaded={() => setUploadedCount((count) => count + 1)}
            />
          )}
        </Card>

        {uploadedCount > 0 && target && (
          <Alert tone="success">
            <FileCheck2 />
            <AlertTitle>Queued for indexing</AlertTitle>
            <AlertDescription>
              Chunking and embedding run in the background. Track progress on the knowledge base.{" "}
              <Link
                href={`/dashboard/${workspaceId}/knowledge/${target.id}`}
                className="inline-flex items-center gap-1 text-primary underline underline-offset-4"
              >
                Open {target.name}
                <ArrowRight className="size-3" aria-hidden="true" />
              </Link>
            </AlertDescription>
          </Alert>
        )}
      </div>

      <div className="space-y-4">
        <Card className="gap-3 p-5">
          <h2 className="text-sm font-medium">Accepted formats</h2>
          <ul className="space-y-1.5">
            {ACCEPTED.map((format) => (
              <li key={format.label} className="flex items-center justify-between text-sm">
                <span>{format.label}</span>
                <code className="font-mono text-xs text-muted-foreground">{format.detail}</code>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="gap-3 p-5">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <ShieldCheck className="size-4 text-success" aria-hidden="true" />
            How uploads are handled
          </h2>
          <ul className="space-y-2 text-xs text-muted-foreground">
            <li>
              Files are identified by their actual content, not their extension — a renamed binary
              is rejected.
            </li>
            <li>
              Stored under a generated name outside any web-served directory; the original filename
              is kept for display only.
            </li>
            <li>Capped at 25 MB per file.</li>
            <li>
              Re-uploading unchanged content is a no-op — it will not duplicate chunks or re-spend
              embedding budget.
            </li>
          </ul>
        </Card>

        <Button variant="outline" className="w-full" asChild>
          <Link href={`/dashboard/${workspaceId}/documents`}>View document library</Link>
        </Button>
      </div>
    </div>
  );
}
