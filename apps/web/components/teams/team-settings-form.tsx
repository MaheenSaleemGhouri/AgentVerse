"use client";

import * as React from "react";

import type { Team } from "@/lib/api/teams";
import { formatMicroUsd } from "@/lib/format";
import { useUpdateTeam } from "@/lib/queries/teams";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

/**
 * Team configuration: objective, shared memory, and the three bounds.
 *
 * All three ceilings are shown together and none can be cleared,
 * because any one alone is insufficient — a loop under the turn limit
 * can still be a cost incident, and one under both can still hang on
 * wall-clock (CLAUDE.md Rule 17). Presenting them as a single group is
 * what makes that legible rather than three unrelated numbers.
 */
export function TeamSettingsForm({
  workspaceId,
  team,
}: {
  workspaceId: string;
  team: Team;
}): React.JSX.Element {
  const update = useUpdateTeam(workspaceId, team.id);

  const [name, setName] = React.useState(team.name);
  const [description, setDescription] = React.useState(team.description ?? "");
  const [objective, setObjective] = React.useState(team.objective ?? "");
  const [maxTurns, setMaxTurns] = React.useState(String(team.max_turns));
  const [maxCost, setMaxCost] = React.useState(String(team.max_cost_micro_usd));
  const [timeout, setTimeout] = React.useState(String(team.timeout_seconds));
  const [sharedMemory, setSharedMemory] = React.useState(team.shared_memory_enabled);

  // The server's values win whenever they change underneath the form —
  // otherwise a save from another tab would be silently overwritten by
  // this one's stale local state.
  React.useEffect(() => {
    setName(team.name);
    setDescription(team.description ?? "");
    setObjective(team.objective ?? "");
    setMaxTurns(String(team.max_turns));
    setMaxCost(String(team.max_cost_micro_usd));
    setTimeout(String(team.timeout_seconds));
    setSharedMemory(team.shared_memory_enabled);
  }, [team]);

  const isDirty =
    name !== team.name ||
    description !== (team.description ?? "") ||
    objective !== (team.objective ?? "") ||
    maxTurns !== String(team.max_turns) ||
    maxCost !== String(team.max_cost_micro_usd) ||
    timeout !== String(team.timeout_seconds) ||
    sharedMemory !== team.shared_memory_enabled;

  function onSave(): void {
    update.mutate({
      name,
      description: description.trim() || null,
      objective: objective.trim() || null,
      max_turns: Number(maxTurns),
      max_cost_micro_usd: Number(maxCost),
      timeout_seconds: Number(timeout),
      shared_memory_enabled: sharedMemory,
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="gap-4 p-5">
        <h2 className="text-sm font-medium">Details</h2>

        <div className="grid gap-2">
          <Label htmlFor="team-name">Name</Label>
          <Input id="team-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="team-description">Description</Label>
          <Input
            id="team-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this team is for"
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="team-objective">Shared objective</Label>
          <Textarea
            id="team-objective"
            rows={3}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="Research a competitor and produce a one-page brief."
          />
          <p className="text-xs text-muted-foreground">
            Prepended to every member&apos;s instructions. Their own instructions still apply and
            come last.
          </p>
        </div>
      </Card>

      <Card className="gap-4 p-5">
        <div>
          <h2 className="text-sm font-medium">Limits</h2>
          <p className="text-xs text-muted-foreground">
            All three apply to a whole session. A team stops at whichever it reaches first — turns
            alone would not catch a run that is cheap per step but never ends.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label htmlFor="team-max-turns">Max turns</Label>
            <Input
              id="team-max-turns"
              type="number"
              min={1}
              max={200}
              value={maxTurns}
              onChange={(e) => setMaxTurns(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="team-max-cost">Cost ceiling (micro-USD)</Label>
            <Input
              id="team-max-cost"
              type="number"
              min={1}
              value={maxCost}
              onChange={(e) => setMaxCost(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {formatMicroUsd(Number(maxCost) || 0)} per session
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="team-timeout">Timeout (seconds)</Label>
            <Input
              id="team-timeout"
              type="number"
              min={5}
              max={3600}
              value={timeout}
              onChange={(e) => setTimeout(e.target.value)}
            />
          </div>
        </div>
      </Card>

      <Card className="gap-4 p-5">
        <h2 className="text-sm font-medium">Shared memory</h2>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <Label htmlFor="team-shared-memory" className="text-sm font-normal">
              Members can read each other&apos;s notes
            </Label>
            <p className="mt-1 text-xs text-muted-foreground">
              Agents save and read findings by key using the <code>remember</code> and{" "}
              <code>recall</code> tools. Turn this off and each member keeps its own private
              memory instead — useful when members should not be influenced by each other.
            </p>
          </div>
          <Switch
            id="team-shared-memory"
            checked={sharedMemory}
            onCheckedChange={setSharedMemory}
          />
        </div>
      </Card>

      <div className="flex items-center justify-end gap-3">
        {isDirty && <span className="text-xs text-warning">Unsaved changes</span>}
        <Button onClick={onSave} disabled={!isDirty || update.isPending}>
          {update.isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  );
}
