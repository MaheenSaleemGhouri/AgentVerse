"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { hrefFor, SIDEBAR_SECTIONS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * The navigation list itself, shared by the desktop rail and the mobile
 * drawer.
 *
 * Factored out so the two presentations cannot drift: a section added to
 * `lib/navigation.ts` appears in both, and the active-route rule is
 * written once. Two copies of "which item is current" is exactly the
 * bug where the phone highlights a different item than the desktop.
 */
export function SidebarNav({
  workspaceId,
  collapsed = false,
  onNavigate,
}: {
  workspaceId: string;
  /** Icon-only rail. Labels move into tooltips and `sr-only` text. */
  collapsed?: boolean;
  /** Called after a link is chosen — the drawer uses it to close. */
  onNavigate?: () => void;
}): React.JSX.Element {
  const pathname = usePathname();
  const workspaceRoot = hrefFor(workspaceId, "");

  return (
    <ul className="flex flex-col gap-0.5">
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
            // Spread rather than `onClick={onNavigate}`: under
            // `exactOptionalPropertyTypes` an explicit `undefined` is not
            // the same as an absent prop, and `LinkProps` does not accept
            // it.
            {...(onNavigate ? { onClick: onNavigate } : {})}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex items-center rounded-lg text-sm font-medium transition-colors",
              "focus-visible:ring-2 focus-visible:ring-sidebar-rail focus-visible:outline-none",
              collapsed ? "h-9 w-9 justify-center" : "gap-3 px-3 py-2",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
            )}
          >
            {/* The active signal is deliberately threefold — a filled
                surface, this terracotta rail, and `aria-current` — so it
                survives a colour-blind read, a greyscale print, and a
                screen reader. Colour alone is never the indicator. */}
            <span
              aria-hidden="true"
              className={cn(
                "absolute top-1/2 -translate-y-1/2 rounded-full bg-sidebar-rail transition-opacity",
                collapsed ? "-left-1.5 h-5 w-0.5" : "left-0 h-5 w-0.5",
                isActive ? "opacity-100" : "opacity-0"
              )}
            />
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            {collapsed ? (
              <span className="sr-only">{item.label}</span>
            ) : (
              <span className="truncate">{item.label}</span>
            )}
            {item.pending && !collapsed && (
              <span className="ml-auto rounded-full bg-sidebar-accent px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-sidebar-muted-foreground uppercase">
                Soon
              </span>
            )}
          </Link>
        );

        // A collapsed rail has no visible labels, so every item needs a
        // tooltip — not only the pending ones.
        const needsTooltip = collapsed || item.pending;
        const tooltip = collapsed
          ? item.pending
            ? `${item.label} — backend ships in a later phase`
            : item.label
          : "Backend ships in a later phase";

        return (
          <li key={item.label}>
            {needsTooltip ? (
              <Tooltip>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right">{tooltip}</TooltipContent>
              </Tooltip>
            ) : (
              link
            )}
          </li>
        );
      })}
    </ul>
  );
}
