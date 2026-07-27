"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { hrefFor, SIDEBAR_SECTIONS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * The fixed AVDS sidebar. Sections never reorder or disappear between
 * screens — a stable spatial model is what makes an app feel like one
 * product rather than a set of pages.
 *
 * Pending sections are shown and navigable rather than hidden: hiding
 * them would make the product look smaller than it is, and their screens
 * state honestly what they are waiting on.
 */
export function Sidebar({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const pathname = usePathname();
  const workspaceRoot = hrefFor(workspaceId, "");

  return (
    <nav
      aria-label="Primary"
      className="flex w-56 shrink-0 flex-col gap-0.5 border-r border-border bg-card/30 px-3 py-4"
    >
      {SIDEBAR_SECTIONS.map((item) => {
        const href = hrefFor(workspaceId, item.segment);
        // The dashboard root would otherwise match every child route.
        const isActive =
          href === workspaceRoot
            ? pathname === workspaceRoot
            : pathname === href || pathname.startsWith(`${href}/`);
        const Icon = item.icon;

        const link = (
          <Link
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            )}
          >
            {/* Active rail — a second, non-colour signal for the current
                section, so active state survives a colour-blind read. */}
            <span
              aria-hidden="true"
              className={cn(
                "absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary transition-opacity",
                isActive ? "opacity-100" : "opacity-0"
              )}
            />
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            <span className="truncate">{item.label}</span>
            {item.pending && (
              <span className="ml-auto rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                Soon
              </span>
            )}
          </Link>
        );

        return item.pending ? (
          <Tooltip key={item.label}>
            <TooltipTrigger asChild>{link}</TooltipTrigger>
            <TooltipContent side="right">Backend ships in a later phase</TooltipContent>
          </Tooltip>
        ) : (
          <React.Fragment key={item.label}>{link}</React.Fragment>
        );
      })}
    </nav>
  );
}
