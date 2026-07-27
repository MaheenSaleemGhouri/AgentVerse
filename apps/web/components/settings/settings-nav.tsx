"use client";

import { Building2, KeyRound, Palette, Shield, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { cn } from "@/lib/utils";

const SECTIONS = [
  { segment: "", label: "Workspace", icon: Building2 },
  { segment: "profile", label: "Profile", icon: User },
  { segment: "api-keys", label: "API keys", icon: KeyRound },
  { segment: "security", label: "Security", icon: Shield },
  { segment: "appearance", label: "Appearance", icon: Palette },
] as const;

export function SettingsNav({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const pathname = usePathname();
  const root = `/dashboard/${workspaceId}/settings`;

  return (
    <nav aria-label="Settings sections" className="flex gap-1 lg:w-52 lg:flex-col">
      {SECTIONS.map((section) => {
        const href = section.segment ? `${root}/${section.segment}` : root;
        const isActive = pathname === href;
        const Icon = section.icon;
        return (
          <Link
            key={section.label}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
              isActive
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            {section.label}
          </Link>
        );
      })}
    </nav>
  );
}
