"use client";

import { FileText, Search, Upload } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { KbDocument } from "@/lib/api/knowledge";
import { formatBytes, formatRelativeTime } from "@/lib/format";

import { DocumentStatusBadge } from "@/components/knowledge/document-status-badge";
import { EmptyState } from "@/components/patterns/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type StatusFilter = "all" | "pending" | "processing" | "indexed" | "failed";

const FILTERS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "indexed", label: "Indexed" },
  { value: "processing", label: "Indexing" },
  { value: "pending", label: "Queued" },
  { value: "failed", label: "Failed" },
];

export function DocumentLibrary({
  workspaceId,
  rows,
}: {
  workspaceId: string;
  rows: Array<{ document: KbDocument; knowledgeBaseName: string }>;
}): React.JSX.Element {
  const [query, setQuery] = React.useState("");
  const [status, setStatus] = React.useState<StatusFilter>("all");

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter(({ document, knowledgeBaseName }) => {
      if (status !== "all" && document.status !== status) return false;
      if (!needle) return true;
      return (
        document.original_filename.toLowerCase().includes(needle) ||
        knowledgeBaseName.toLowerCase().includes(needle)
      );
    });
  }, [rows, query, status]);

  const failedCount = rows.filter((row) => row.document.status === "failed").length;

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No documents yet"
        description="Upload a PDF, Word file, Markdown, text, CSV, or JSON — your agents can cite it as soon as indexing finishes."
        action={
          <Button asChild>
            <Link href={`/dashboard/${workspaceId}/upload`}>
              <Upload />
              Upload documents
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by filename or knowledge base…"
            aria-label="Search documents"
            className="pl-9"
          />
        </div>
        <Tabs value={status} onValueChange={(value) => setStatus(value as StatusFilter)}>
          <TabsList>
            {FILTERS.map((filter) => (
              <TabsTrigger key={filter.value} value={filter.value}>
                {filter.label}
                {filter.value === "failed" && failedCount > 0 && (
                  <span className="ml-1.5 rounded-full bg-destructive px-1.5 text-[10px] text-destructive-foreground">
                    {failedCount}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No documents match"
          description="Try a different search term, or clear the status filter."
          action={
            <Button
              variant="outline"
              onClick={() => {
                setQuery("");
                setStatus("all");
              }}
            >
              Clear filters
            </Button>
          }
        />
      ) : (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Knowledge base</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Chunks</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Added</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map(({ document, knowledgeBaseName }) => (
                <TableRow key={document.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <FileText
                        className="size-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                      <span className="truncate font-medium">{document.original_filename}</span>
                    </div>
                    {document.error_message && (
                      <p className="mt-1 text-xs text-destructive">{document.error_message}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/dashboard/${workspaceId}/knowledge/${document.knowledge_base_id}`}
                      className="text-sm hover:underline"
                    >
                      {knowledgeBaseName}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatBytes(document.size_bytes)}
                  </TableCell>
                  <TableCell className="text-sm tabular-nums text-muted-foreground">
                    {document.status === "indexed" ? document.chunk_count : "—"}
                  </TableCell>
                  <TableCell>
                    <DocumentStatusBadge status={document.status} />
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(document.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
