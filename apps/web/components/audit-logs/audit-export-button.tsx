"use client";

import { Download } from "lucide-react";
import * as React from "react";

import { auditExportPath } from "@/lib/download-paths";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/**
 * Downloads the workspace's audit log.
 *
 * Rendered as real links rather than click handlers: a link is what a
 * download is, so it keeps middle-click and "save link as", and needs
 * no JavaScript to work.
 */
export function AuditExportButton({
  workspaceId,
}: {
  workspaceId: string;
}): React.JSX.Element {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Download aria-hidden="true" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <a href={auditExportPath(workspaceId, "csv")} download>
            Download CSV
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={auditExportPath(workspaceId, "json")} download>
            Download JSON
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
