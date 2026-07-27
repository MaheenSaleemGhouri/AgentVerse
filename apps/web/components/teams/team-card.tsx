"use client";

import { Copy, MoreVertical, Trash2, Users2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Team } from "@/lib/api/teams";
import { formatRelativeTime } from "@/lib/format";
import { useDeleteTeam, useDuplicateTeam } from "@/lib/queries/teams";
import { TEAM_ROLES, TOPOLOGIES } from "@/lib/teams-vocabulary";
import { cn } from "@/lib/utils";

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
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * The team tile, composed from the same primitives as `AgentCard` so
 * the two lists read as one product rather than two features.
 *
 * Deletion goes through `AlertDialog` — a team's session history stays
 * resolvable, but the team disappears from every list, and confirmation
 * friction scales with reversibility (CLAUDE.md §15).
 */
export function TeamCard({
  workspaceId,
  team,
}: {
  workspaceId: string;
  team: Team;
}): React.JSX.Element {
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const deleteTeam = useDeleteTeam(workspaceId);
  const duplicateTeam = useDuplicateTeam(workspaceId);

  const topology = TOPOLOGIES[team.topology];
  const TopologyIcon = topology.icon;
  const detailHref = `/dashboard/${workspaceId}/teams/${team.id}`;

  return (
    <Card className="group relative gap-0 p-5 transition-colors hover:border-primary/40">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
        >
          <Users2 className="size-4.5" />
        </span>

        <div className="min-w-0 flex-1">
          <Link
            href={detailHref}
            className="font-medium after:absolute after:inset-0 after:content-[''] hover:underline"
          >
            {team.name}
          </Link>
          <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
            {team.description ?? topology.summary}
          </p>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="relative z-10 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
              aria-label={`Actions for ${team.name}`}
            >
              <MoreVertical />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => duplicateTeam.mutate(team.id)}>
              <Copy />
              Duplicate
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmOpen(true)}>
              <Trash2 />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="gap-1.5">
          <TopologyIcon className="size-3" aria-hidden="true" />
          {topology.label}
        </Badge>
        <Badge variant="secondary">
          {team.members.length} {team.members.length === 1 ? "agent" : "agents"}
        </Badge>
        {!team.shared_memory_enabled && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="text-muted-foreground">
                Memory not shared
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              Members keep private memory — they cannot read each other&apos;s notes.
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      {team.members.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {team.members.slice(0, 5).map((member) => {
            const role = TEAM_ROLES[member.role];
            const RoleIcon = role.icon;
            return (
              <span
                key={member.id}
                className="inline-flex items-center gap-1 rounded-md border border-border px-1.5 py-0.5 text-xs text-muted-foreground"
              >
                <RoleIcon className="size-3" aria-hidden="true" />
                {role.label}
              </span>
            );
          })}
          {team.members.length > 5 && (
            <span className="self-center text-xs text-muted-foreground">
              +{team.members.length - 5} more
            </span>
          )}
        </div>
      )}

      <p className="mt-4 text-xs text-muted-foreground">
        Updated {formatRelativeTime(team.updated_at)}
      </p>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {team.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              The team is removed from every list. Its past sessions stay readable, and the
              agents on it are not affected — they keep working on their own and on any other
              team.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() => deleteTeam.mutate(team.id)}
            >
              Delete team
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
