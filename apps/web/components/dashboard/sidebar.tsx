"use client";

import {
  Bot,
  ChartColumnBig,
  CreditCard,
  LayoutDashboard,
  Plug,
  Settings,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: (workspaceId: string) => string;
  icon: React.ComponentType<{ className?: string }>;
  /** Sections not yet built in this phase — shown, not hidden, per the
   * AVDS design bible's fixed sidebar structure, but disabled rather
   * than linking to a page that doesn't exist yet. */
  comingSoon?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: (id) => `/dashboard/${id}`, icon: LayoutDashboard },
  { label: "Agents", href: (id) => `/dashboard/${id}/agents`, icon: Bot },
  { label: "Knowledge", href: () => "#", icon: Sparkles, comingSoon: true },
  { label: "MCP", href: () => "#", icon: Plug, comingSoon: true },
  { label: "Workflows", href: () => "#", icon: Workflow, comingSoon: true },
  { label: "Analytics", href: () => "#", icon: ChartColumnBig, comingSoon: true },
  { label: "Team", href: (id) => `/dashboard/${id}`, icon: Users },
  { label: "Billing", href: () => "#", icon: CreditCard, comingSoon: true },
  { label: "Settings", href: () => "#", icon: Settings, comingSoon: true },
];

export function Sidebar({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="flex w-60 shrink-0 flex-col gap-1 border-r border-border bg-card/40 p-3"
    >
      <div className="px-2 py-3 text-sm font-semibold tracking-tight">AgentVerse</div>
      {NAV_ITEMS.map((item) => {
        const href = item.href(workspaceId);
        const isActive = !item.comingSoon && (pathname === href || pathname.startsWith(`${href}/`));
        const Icon = item.icon;

        if (item.comingSoon) {
          return (
            <span
              key={item.label}
              aria-disabled="true"
              className="flex cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground/60"
            >
              <Icon className="size-4" />
              {item.label}
              <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                Soon
              </span>
            </span>
          );
        }

        return (
          <Link
            key={item.label}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-accent text-accent-foreground"
                : "text-foreground/80 hover:bg-accent/60 hover:text-accent-foreground"
            )}
          >
            <Icon className="size-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
