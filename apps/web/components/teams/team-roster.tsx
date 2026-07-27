"use client";

import { GripVertical, Plus, Trash2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { Team, TeamMember, TeamRole } from "@/lib/api/teams";
import { useAddTeamMember, useRemoveTeamMember, useReorderTeamMembers } from "@/lib/queries/teams";
import { ROLE_ORDER, TEAM_ROLES, TOPOLOGIES } from "@/lib/teams-vocabulary";
import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/patterns/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * What this team still needs before it can run.
 *
 * Mirrors the executor's own preconditions rather than inventing UI-only
 * rules — the point is that the user sees the same requirement the
 * backend will enforce, before submitting, instead of discovering it
 * from a failed session.
 */
function missingRequirements(team: Team, publishedAgentIds: ReadonlySet<string>): string[] {
  const problems: string[] = [];
  const roles = team.members.map((member) => member.role);

  if (team.members.length === 0) {
    problems.push("Add at least one agent.");
    return problems;
  }
  if (!team.members.some((member) => publishedAgentIds.has(member.agent_id))) {
    problems.push("No member's agent is published yet — publish at least one.");
  }
  if (team.topology === "supervisor_worker") {
    if (!roles.includes("supervisor")) problems.push("Assign one member the supervisor role.");
    else if (
      !team.members.some(
        (member) => member.role !== "supervisor" && member.can_receive_handoff
      )
    ) {
      problems.push("The supervisor has no one to delegate to.");
    }
  }
  if (team.topology === "planner_executor_critic") {
    for (const required of ["planner", "executor", "critic"] as const) {
      if (!roles.includes(required)) problems.push(`Assign one member the ${required} role.`);
    }
  }
  if (team.topology === "parallel" && team.members.length < 2 && roles.includes("aggregator")) {
    problems.push("Add at least one member besides the aggregator.");
  }
  return problems;
}

/**
 * The team roster: drag to reorder, assign roles, add and remove agents.
 *
 * Reordering is optimistic — the list moves under the pointer
 * immediately and the server call follows — because a drag that snaps
 * back while a request is in flight reads as a failure even when it
 * succeeds. A rejected reorder refetches rather than replaying the old
 * array, since the server's order is what actually decides execution.
 *
 * Keyboard parity is not arrow-key drag emulation: each row exposes
 * explicit "move up"/"move down" buttons, which is the select-then-act
 * model CLAUDE.md §15 requires for reorderable lists.
 */
export function TeamRoster({
  workspaceId,
  team,
  agents,
}: {
  workspaceId: string;
  team: Team;
  agents: Agent[];
}): React.JSX.Element {
  const addMember = useAddTeamMember(workspaceId, team.id);
  const removeMember = useRemoveTeamMember(workspaceId, team.id);
  const reorder = useReorderTeamMembers(workspaceId, team.id);

  const [order, setOrder] = React.useState<TeamMember[]>(team.members);
  const [draggingId, setDraggingId] = React.useState<string | null>(null);

  // The server's order wins whenever it changes underneath us — a stale
  // local array would silently misreport a sequential team's run order.
  React.useEffect(() => setOrder(team.members), [team.members]);

  const agentsById = React.useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent])),
    [agents]
  );
  const publishedAgentIds = React.useMemo(
    () => new Set(agents.filter((a) => a.published_version_id !== null).map((a) => a.id)),
    [agents]
  );
  const available = agents.filter(
    (agent) => !team.members.some((member) => member.agent_id === agent.id)
  );
  const problems = missingRequirements(team, publishedAgentIds);

  function commit(next: TeamMember[]): void {
    setOrder(next);
    reorder.mutate(next.map((member) => member.id));
  }

  function move(index: number, delta: number): void {
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    const next = [...order];
    const [moved] = next.splice(index, 1);
    if (!moved) return;
    next.splice(target, 0, moved);
    commit(next);
  }

  function onDrop(targetIndex: number): void {
    if (!draggingId) return;
    const from = order.findIndex((member) => member.id === draggingId);
    setDraggingId(null);
    if (from === -1 || from === targetIndex) return;
    const next = [...order];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    next.splice(targetIndex, 0, moved);
    commit(next);
  }

  return (
    <div className="flex flex-col gap-4">
      {problems.length > 0 && (
        <Alert tone="warning">
          <TriangleAlert />
          <AlertTitle>This team cannot run yet</AlertTitle>
          <AlertDescription>
            <ul className="list-inside list-disc space-y-0.5">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {order.length === 0 ? (
        <EmptyState
          icon={Plus}
          title="No agents on this team"
          description={TOPOLOGIES[team.topology].requires}
        />
      ) : (
        <ol className="flex flex-col gap-2">
          {order.map((member, index) => {
            const agent = agentsById.get(member.agent_id);
            const role = TEAM_ROLES[member.role];
            const RoleIcon = role.icon;
            const isPublished = publishedAgentIds.has(member.agent_id);

            return (
              <li
                key={member.id}
                draggable
                onDragStart={() => setDraggingId(member.id)}
                onDragEnd={() => setDraggingId(null)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => onDrop(index)}
                className={cn(
                  "flex items-center gap-3 rounded-lg border border-border bg-card p-3",
                  draggingId === member.id && "opacity-50"
                )}
              >
                <span
                  className="cursor-grab text-muted-foreground active:cursor-grabbing"
                  aria-hidden="true"
                >
                  <GripVertical className="size-4" />
                </span>

                {/* Position is meaningful only where order decides
                    execution; showing it for a supervisor team would
                    imply a sequence that does not exist. */}
                {team.topology === "sequential" && (
                  <span className="w-5 text-center font-mono text-xs text-muted-foreground">
                    {index + 1}
                  </span>
                )}

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/dashboard/${workspaceId}/agents/${member.agent_id}`}
                      className="truncate text-sm font-medium hover:underline"
                    >
                      {agent?.name ?? "Unknown agent"}
                    </Link>
                    {!isPublished && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge variant="outline" className="text-warning">
                            Not published
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          This agent is skipped at run time until a version is published.
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">{role.summary}</p>
                </div>

                <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
                  <RoleIcon className="size-3.5" aria-hidden="true" />
                  {role.label}
                </span>

                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => move(index, -1)}
                    disabled={index === 0}
                    aria-label={`Move ${agent?.name ?? "member"} up`}
                  >
                    ↑
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => move(index, 1)}
                    disabled={index === order.length - 1}
                    aria-label={`Move ${agent?.name ?? "member"} down`}
                  >
                    ↓
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => removeMember.mutate(member.id)}
                    aria-label={`Remove ${agent?.name ?? "member"} from team`}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <Card className="gap-3 p-4">
        <h3 className="text-sm font-medium">Add an agent</h3>
        {available.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Every agent in this workspace is already on the team.{" "}
            <Link
              href={`/dashboard/${workspaceId}/agents`}
              className="underline underline-offset-2"
            >
              Create another agent
            </Link>{" "}
            to add it here.
          </p>
        ) : (
          <AddMemberForm
            available={available}
            onAdd={(agentId, role) =>
              addMember.mutate({
                agent_id: agentId,
                role,
                position: order.length,
                handoff_description: null,
                can_receive_handoff: true,
              })
            }
            pending={addMember.isPending}
          />
        )}
      </Card>
    </div>
  );
}

function AddMemberForm({
  available,
  onAdd,
  pending,
}: {
  available: Agent[];
  onAdd: (agentId: string, role: TeamRole) => void;
  pending: boolean;
}): React.JSX.Element {
  const [agentId, setAgentId] = React.useState("");
  const [role, setRole] = React.useState<TeamRole>("worker");

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="min-w-48 flex-1">
        <label htmlFor="add-member-agent" className="mb-1.5 block text-xs text-muted-foreground">
          Agent
        </label>
        <Select value={agentId} onValueChange={setAgentId}>
          <SelectTrigger id="add-member-agent" className="w-full">
            <SelectValue placeholder="Choose an agent" />
          </SelectTrigger>
          <SelectContent>
            {available.map((agent) => (
              <SelectItem key={agent.id} value={agent.id}>
                {agent.name}
                {agent.published_version_id === null ? " (draft)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="min-w-40">
        <label htmlFor="add-member-role" className="mb-1.5 block text-xs text-muted-foreground">
          Role on this team
        </label>
        <Select value={role} onValueChange={(value) => setRole(value as TeamRole)}>
          <SelectTrigger id="add-member-role" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROLE_ORDER.map((option) => (
              <SelectItem key={option} value={option}>
                {TEAM_ROLES[option].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button onClick={() => agentId && onAdd(agentId, role)} disabled={!agentId || pending}>
        <Plus />
        Add
      </Button>
    </div>
  );
}
