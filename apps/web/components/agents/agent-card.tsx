"use client";

import { Bot, MessageSquare, MoreVertical, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import { formatRelativeTime } from "@/lib/format";
import { useDeleteAgent } from "@/lib/queries/agents";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The agent tile used on both the dashboard and the agents list —
 * composed from Card + Badge + DropdownMenu rather than a bespoke div,
 * so focus handling and menu keyboard nav come from the primitives.
 *
 * Deletion goes through `AlertDialog`, not a one-click menu item:
 * deleting an agent takes its versions and run history with it, and
 * confirmation friction scales with reversibility (CLAUDE.md §15).
 */
export function AgentCard({
  workspaceId,
  agent,
}: {
  workspaceId: string;
  agent: Agent;
}): React.JSX.Element {
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const deleteAgent = useDeleteAgent(workspaceId);
  const detailHref = `/dashboard/${workspaceId}/agents/${agent.id}`;

  return (
    <Card className="group gap-0 p-5 transition-colors hover:border-primary/40">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
        >
          <Bot className="size-4.5" />
        </span>

        <div className="min-w-0 flex-1">
          <Link
            href={detailHref}
            // The whole card is the target; the overlay keeps one link
            // in the a11y tree instead of nesting interactive elements.
            className="font-medium after:absolute after:inset-0 after:content-[''] hover:underline"
          >
            {agent.name}
          </Link>
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
            {agent.description ?? "No description"}
          </p>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              // Above the card-wide link overlay so the menu stays clickable.
              className="relative z-10 shrink-0"
              aria-label={`Actions for ${agent.name}`}
            >
              <MoreVertical />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem asChild>
              <Link href={`${detailHref}/builder`}>
                <Pencil className="size-4" />
                Open builder
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href={`/dashboard/${workspaceId}/playground?agent=${agent.id}`}>
                <MessageSquare className="size-4" />
                Test in playground
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onSelect={(event) => {
                event.preventDefault();
                setConfirmOpen(true);
              }}
            >
              <Trash2 className="size-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <AgentStatusBadge status={agent.status} />
        <span className="ml-auto text-xs text-muted-foreground">
          Updated {formatRelativeTime(agent.updated_at)}
        </span>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{agent.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Its versions and configuration go with it. Anything calling this agent by ID will
              start failing.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() => deleteAgent.mutate(agent.id)}
            >
              Delete agent
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
