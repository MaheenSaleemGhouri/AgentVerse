import { BookOpen, Bot, MessageSquare, Upload } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Card } from "@/components/ui/card";

const ACTIONS = [
  {
    label: "Build an agent",
    description: "Instructions, model, tools",
    href: (id: string) => `/dashboard/${id}/agents`,
    icon: Bot,
  },
  {
    label: "Add knowledge",
    description: "Ground answers in your docs",
    href: (id: string) => `/dashboard/${id}/knowledge`,
    icon: BookOpen,
  },
  {
    label: "Upload documents",
    description: "PDF, Word, Markdown, CSV",
    href: (id: string) => `/dashboard/${id}/upload`,
    icon: Upload,
  },
  {
    label: "Open playground",
    description: "Run an agent and watch it work",
    href: (id: string) => `/dashboard/${id}/playground`,
    icon: MessageSquare,
  },
] as const;

export function QuickActions({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {ACTIONS.map((action) => {
        const Icon = action.icon;
        return (
          <Card
            key={action.label}
            className="group relative gap-0 p-4 transition-colors hover:border-primary/40 hover:bg-accent/30"
          >
            <span
              aria-hidden="true"
              className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground"
            >
              <Icon className="size-4" />
            </span>
            <Link
              href={action.href(workspaceId)}
              className="mt-3 text-sm font-medium after:absolute after:inset-0 after:content-['']"
            >
              {action.label}
            </Link>
            <p className="mt-0.5 text-xs text-muted-foreground">{action.description}</p>
          </Card>
        );
      })}
    </div>
  );
}
