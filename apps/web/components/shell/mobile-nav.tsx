"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { hrefFor } from "@/lib/navigation";

import { AgentVerseMark } from "@/components/brand/agentverse-mark";
import { SidebarNav } from "@/components/shell/sidebar-nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/**
 * Navigation below the `md` breakpoint, where the rail has no room.
 *
 * A drawer rather than a bottom tab bar: the product has nine primary
 * sections and a tab bar holds four or five before it starts hiding
 * things behind "More" — which is a worse version of this drawer with
 * an extra tap in front of it.
 *
 * Radix supplies the focus trap, the Escape handler and the scroll lock.
 * Closing on navigation is the one behaviour it cannot know about, and
 * is handled here.
 */
export function MobileNav({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const pathname = usePathname();

  // A drawer left open across a route change would cover the page the
  // user just asked for. Keyed on `pathname` so it also closes when
  // navigation comes from somewhere else — a command-palette jump, say.
  React.useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open navigation">
          <Menu />
        </Button>
      </SheetTrigger>

      <SheetContent side="left" className="w-72 border-sidebar-border bg-sidebar p-0">
        <SheetHeader className="border-sidebar-border px-4 py-3">
          <SheetTitle className="flex items-center gap-2 text-sidebar-foreground">
            <AgentVerseMark className="size-6" />
            <span className="font-display text-[15px] font-bold tracking-tight">AgentVerse</span>
          </SheetTitle>
          <SheetDescription className="sr-only">
            Primary navigation for this workspace
          </SheetDescription>
        </SheetHeader>

        <nav aria-label="Primary" className="px-3 py-3">
          <SidebarNav workspaceId={workspaceId} onNavigate={() => setOpen(false)} />
        </nav>

        <div className="mt-auto border-t border-sidebar-border p-3">
          <Link
            href={hrefFor(workspaceId, "settings")}
            onClick={() => setOpen(false)}
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
          >
            Settings
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}
