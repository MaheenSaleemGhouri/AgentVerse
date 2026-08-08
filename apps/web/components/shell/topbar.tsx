"use client";

import { Bell, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { DocsSearchEntry } from "@/lib/docs/match";
import type { Workspace } from "@/lib/api/workspaces";

import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { CommandPalette } from "@/components/shell/command-palette";
import { MobileNav } from "@/components/shell/mobile-nav";
import { ShortcutHint } from "@/components/shell/shortcut-hint";
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
  docsIndex,
}: {
  workspaces: Workspace[];
  activeWorkspaceId: string;
  userEmail: string;
  userName?: string | null | undefined;
  /** Built server-side in the layout and passed straight through to the
   * palette — the docs corpus is public and identical for everyone, so
   * it ships with the shell rather than being fetched per search. */
  docsIndex: readonly DocsSearchEntry[];
}): React.JSX.Element {
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur-md sm:gap-3 sm:px-4">
      {/* The brand lives on the sidebar now, so the top bar starts with
          the drawer trigger on phones and with the workspace everywhere
          else — one identity, stated once. */}
      <MobileNav workspaceId={activeWorkspaceId} />

      <WorkspaceSwitcher workspaces={workspaces} activeWorkspaceId={activeWorkspaceId} />

      <div className="ml-2 hidden min-w-0 lg:block">
        <Breadcrumbs workspaceId={activeWorkspaceId} />
      </div>

      <div className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="sm" className="hidden text-muted-foreground md:inline-flex" asChild>
          <Link href="/docs">Docs</Link>
        </Button>

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
              <ShortcutHint />
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

      <CommandPalette workspaceId={activeWorkspaceId} docsIndex={docsIndex} />
    </header>
  );
}
