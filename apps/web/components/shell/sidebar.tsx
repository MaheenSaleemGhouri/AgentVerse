"use client";

import { PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { hrefFor } from "@/lib/navigation";
import { useSidebarCollapsed } from "@/lib/hooks/useSidebarCollapsed";
import { cn } from "@/lib/utils";

import { AgentVerseMark } from "@/components/brand/agentverse-mark";
import { SidebarNav } from "@/components/shell/sidebar-nav";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * The desktop sidebar: brand, navigation, settings.
 *
 * Dark in both themes, which is how the approved reference draws it
 * (panel 05). It is not `--card` with a filter — it has its own token
 * set, so the rail stays the frame around the content in light and dark
 * alike.
 *
 * Three widths, one component:
 *   ≥1024px  full, collapsible to a 64px rail and remembered
 *   768px    always the rail — a tablet has room for icons, not labels
 *   <768px   hidden; the drawer in `MobileNav` takes over
 *
 * Sections never reorder or disappear between screens. A stable spatial
 * model is most of what makes an app feel like one product.
 */
export function Sidebar({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const { collapsed, toggle, ready } = useSidebarCollapsed();

  // Below `lg` the rail is forced regardless of preference, so the
  // layout is driven by both the breakpoint and the stored choice.
  const railOnly = collapsed;

  return (
    <nav
      aria-label="Primary"
      data-collapsed={railOnly}
      className={cn(
        "hidden shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex",
        // Tailwind cannot express "rail below lg, preference at lg", so
        // the width is two rules: always a rail on tablet, the stored
        // preference from `lg` up.
        "w-16",
        railOnly ? "lg:w-16" : "lg:w-60",
        // Skipped until the stored preference is known, so a restored
        // collapsed sidebar does not animate open on every page load.
        ready && "transition-[width] duration-200 motion-reduce:transition-none"
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center border-b border-sidebar-border",
          railOnly ? "justify-center px-2" : "justify-center px-2 lg:justify-between lg:px-4"
        )}
      >
        <Link
          href={hrefFor(workspaceId, "")}
          className="flex items-center gap-2 rounded-md focus-visible:ring-2 focus-visible:ring-sidebar-rail focus-visible:outline-none"
        >
          <AgentVerseMark className="size-7 shrink-0" />
          <span
            className={cn(
              "font-display text-[15px] font-bold tracking-tight text-sidebar-foreground",
              railOnly ? "sr-only" : "sr-only lg:not-sr-only"
            )}
          >
            AgentVerse
          </span>
        </Link>

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={toggle}
              aria-expanded={!railOnly}
              aria-label={railOnly ? "Expand sidebar" : "Collapse sidebar"}
              className="hidden size-7 items-center justify-center rounded-md text-sidebar-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-sidebar-rail focus-visible:outline-none lg:inline-flex"
            >
              {railOnly ? (
                <PanelLeftOpen className="size-4" aria-hidden="true" />
              ) : (
                <PanelLeftClose className="size-4" aria-hidden="true" />
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {railOnly ? "Expand sidebar" : "Collapse sidebar"}
          </TooltipContent>
        </Tooltip>
      </div>

      <div className={cn("flex-1 overflow-y-auto py-3", railOnly ? "px-3" : "px-3")}>
        {/* The rail below `lg` is a layout fact, not a preference, so the
            nav is rendered twice and each copy is hidden at the widths
            where the other is correct. Passing one `collapsed` boolean
            would need a resize listener to stay truthful. */}
        <div className="lg:hidden">
          <SidebarNav workspaceId={workspaceId} collapsed />
        </div>
        <div className="hidden lg:block">
          <SidebarNav workspaceId={workspaceId} collapsed={railOnly} />
        </div>
      </div>

      <div className="border-t border-sidebar-border p-3">
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href={hrefFor(workspaceId, "settings")}
              className={cn(
                "flex items-center rounded-lg text-sm font-medium text-sidebar-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-sidebar-rail focus-visible:outline-none",
                railOnly ? "h-9 w-9 justify-center" : "h-9 w-9 justify-center lg:w-auto lg:justify-start lg:gap-3 lg:px-3"
              )}
            >
              <Settings className="size-4 shrink-0" aria-hidden="true" />
              <span className={cn(railOnly ? "sr-only" : "sr-only lg:not-sr-only")}>
                Settings
              </span>
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right">Settings</TooltipContent>
        </Tooltip>
      </div>
    </nav>
  );
}
