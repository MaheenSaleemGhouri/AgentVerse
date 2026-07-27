"use client";

import { Bell, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Workspace } from "@/lib/api/workspaces";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { CommandPalette } from "@/components/shell/command-palette";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { UserMenu } from "@/components/shell/user-menu";
import { WorkspaceSwitcher } from "@/components/shell/workspace-switcher";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * The persistent top bar: workspace identity on the left, wayfinding in
 * the middle, account controls on the right.
 *
 * The search affordance is a visible button rather than palette-only —
 * ⌘K is the fast path for people who know it, and a discoverable
 * control is how everyone else finds out it exists.
 */
export function Topbar({
  workspaces,
  activeWorkspaceId,
  userEmail,
  userName,
}: {
  workspaces: Workspace[];
  activeWorkspaceId: string;
  userEmail: string;
  userName?: string | null | undefined;
}): React.JSX.Element {
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md">
      <Link href={`/dashboard/${activeWorkspaceId}`} className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="flex size-7 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground"
        >
          A
        </span>
        <span className="text-sm font-semibold tracking-tight">AgentVerse</span>
      </Link>

      <Separator orientation="vertical" className="h-5" />

      <WorkspaceSwitcher workspaces={workspaces} activeWorkspaceId={activeWorkspaceId} />

      <div className="ml-2 hidden min-w-0 lg:block">
        <Breadcrumbs workspaceId={activeWorkspaceId} />
      </div>

      <div className="ml-auto flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="hidden gap-2 text-muted-foreground md:inline-flex"
              onClick={() =>
                document.dispatchEvent(
                  new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true })
                )
              }
            >
              <Search className="size-3.5" />
              <span>Search</span>
              <kbd className="rounded border border-border bg-muted px-1 font-mono text-[10px]">
                ⌘K
              </kbd>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Search pages and actions</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" asChild aria-label="Notifications">
              <Link href={`/dashboard/${activeWorkspaceId}/notifications`}>
                <Bell />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Notifications</TooltipContent>
        </Tooltip>

        <ThemeToggle />

        <Separator orientation="vertical" className="mx-1 h-5" />

        <UserMenu email={userEmail} name={userName} workspaceId={activeWorkspaceId} />
      </div>

      <CommandPalette workspaceId={activeWorkspaceId} />
    </header>
  );
}
