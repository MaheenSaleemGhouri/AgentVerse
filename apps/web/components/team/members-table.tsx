"use client";

import { MoreVertical, Shield, UserMinus, Users } from "lucide-react";
import * as React from "react";

import type { Member, Role } from "@/lib/api/workspaces";
import { formatRelativeTime, initialsFrom } from "@/lib/format";
import { useChangeMemberRole, useMembers, useRemoveMember } from "@/lib/queries/workspace";
import { ASSIGNABLE_ROLES, ROLE_DESCRIPTIONS, outranks } from "@/lib/roles";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StatusBadge } from "@/components/patterns/status-badge";
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
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const ROLE_TONE: Record<Role, "brand" | "info" | "neutral"> = {
  owner: "brand",
  admin: "info",
  member: "neutral",
  viewer: "neutral",
};

export function MembersTable({
  workspaceId,
  initialMembers,
  viewerRole,
  canManage,
}: {
  workspaceId: string;
  initialMembers: Member[];
  viewerRole: Role;
  canManage: boolean;
}): React.JSX.Element {
  const { data: members, isError, refetch } = useMembers(workspaceId, initialMembers);
  const changeRole = useChangeMemberRole(workspaceId);
  const removeMember = useRemoveMember(workspaceId);
  const [pendingRemoval, setPendingRemoval] = React.useState<Member | null>(null);

  if (isError) {
    return (
      <ErrorState
        title="Could not load members"
        description="The workspace API did not respond."
        onRetry={() => void refetch()}
      />
    );
  }

  if ((members ?? []).length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No members yet"
        description="Add a teammate by their user ID to give them access to this workspace."
      />
    );
  }

  return (
    <>
      <Card className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Joined</TableHead>
              {canManage && <TableHead className="w-12" />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {(members ?? []).map((member) => {
              // A member can never act on someone at or above their own
              // rank — the same rule the API enforces (CLAUDE.md §10).
              const actionable = canManage && outranks(viewerRole, member.role);

              return (
                <TableRow key={member.user_id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Avatar className="size-8">
                        <AvatarFallback>{initialsFrom(member.user_id)}</AvatarFallback>
                      </Avatar>
                      <code className="font-mono text-xs text-muted-foreground">
                        {member.user_id}
                      </code>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-block">
                          <StatusBadge tone={ROLE_TONE[member.role]}>
                            <span className="capitalize">{member.role}</span>
                          </StatusBadge>
                        </span>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-64">
                        {ROLE_DESCRIPTIONS[member.role]}
                      </TooltipContent>
                    </Tooltip>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(member.created_at)}
                  </TableCell>
                  {canManage && (
                    <TableCell>
                      {actionable ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Actions for ${member.user_id}`}
                            >
                              <MoreVertical />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-48">
                            <DropdownMenuLabel className="text-xs">Change role</DropdownMenuLabel>
                            {ASSIGNABLE_ROLES.map((role) => (
                              <DropdownMenuItem
                                key={role}
                                disabled={role === member.role || changeRole.isPending}
                                onSelect={() =>
                                  changeRole.mutate({ targetUserId: member.user_id, role })
                                }
                              >
                                <Shield className="size-4" />
                                <span className="capitalize">{role}</span>
                                {role === member.role && (
                                  <span
                                    className="ml-auto size-1.5 rounded-full bg-primary"
                                    aria-hidden="true"
                                  />
                                )}
                              </DropdownMenuItem>
                            ))}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={(event) => {
                                event.preventDefault();
                                setPendingRemoval(member);
                              }}
                            >
                              <UserMinus className="size-4" />
                              Remove
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span tabIndex={0} className="inline-flex">
                              <Button variant="ghost" size="icon-sm" disabled aria-label="No actions available">
                                <MoreVertical />
                              </Button>
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            You cannot change someone at or above your own role.
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      <AlertDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => !open && setPendingRemoval(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this member?</AlertDialogTitle>
            <AlertDialogDescription>
              They lose access to every agent, knowledge base, and run in this workspace
              immediately. Anything they created stays.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() => {
                if (pendingRemoval) removeMember.mutate(pendingRemoval.user_id);
                setPendingRemoval(null);
              }}
            >
              Remove member
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
