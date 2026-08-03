"use client";

import { Plus, ShieldCheck, Trash2 } from "lucide-react";
import * as React from "react";

import type { CustomRole, Permission, RoleDescriptor } from "@/lib/api/roles";
import type { Role } from "@/lib/api/workspaces";
import { ROLE_DESCRIPTIONS } from "@/lib/roles";
import {
  useBuiltinRoles,
  useCreateCustomRole,
  useCustomRoles,
  useDeleteCustomRole,
} from "@/lib/queries/roles";

import { EmptyState } from "@/components/patterns/empty-state";
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
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/** Groups `agent:view`, `agent:run`, … under one heading per resource. */
function groupByResource(permissions: readonly Permission[]): Map<string, Permission[]> {
  const grouped = new Map<string, Permission[]>();
  for (const permission of permissions) {
    const [resource = "other"] = permission.split(":");
    const bucket = grouped.get(resource) ?? [];
    bucket.push(permission);
    grouped.set(resource, bucket);
  }
  return grouped;
}

function formatResource(resource: string): string {
  return resource.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * The role model: the seven built-in tiers and their inherited
 * permissions, plus any roles this workspace has defined itself.
 *
 * The built-in matrix is rendered from what the API returns, never from
 * a copy kept here — the server enforces it, so the server describes it,
 * and the two cannot drift.
 */
export function RolesPanel({
  workspaceId,
  canManage,
  initialBuiltinRoles,
  initialCustomRoles,
}: {
  workspaceId: string;
  /** Admin or above. Non-admins still see the matrix; they just can't edit. */
  canManage: boolean;
  initialBuiltinRoles: RoleDescriptor[];
  initialCustomRoles: CustomRole[];
}): React.JSX.Element {
  const { data: builtinRoles } = useBuiltinRoles(workspaceId, initialBuiltinRoles);
  const { data: customRoles } = useCustomRoles(workspaceId, initialCustomRoles);
  const createRole = useCreateCustomRole(workspaceId);
  const deleteRole = useDeleteCustomRole(workspaceId);

  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [baseRole, setBaseRole] = React.useState<Role>("member");
  const [selected, setSelected] = React.useState<Set<Permission>>(new Set());
  const [pendingDelete, setPendingDelete] = React.useState<CustomRole | null>(null);

  const allPermissions = React.useMemo(
    () => builtinRoles?.find((entry) => entry.role === "owner")?.permissions ?? [],
    [builtinRoles]
  );

  /** Grants the base tier already inherits — shown checked and locked, so
   *  nobody re-grants something they already have and thinks it did work. */
  const inherited = React.useMemo(
    () =>
      new Set(builtinRoles?.find((entry) => entry.role === baseRole)?.permissions ?? []),
    [builtinRoles, baseRole]
  );

  function togglePermission(permission: Permission): void {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(permission)) {
        next.delete(permission);
      } else {
        next.add(permission);
      }
      return next;
    });
  }

  function submit(): void {
    createRole.mutate(
      {
        name: name.trim(),
        description: description.trim() || null,
        base_role: baseRole,
        // Inherited grants are omitted: storing them would be redundant
        // and would make a later change to the base tier's matrix
        // silently frozen into this role.
        permissions: [...selected].filter((p) => !inherited.has(p)),
      },
      {
        onSuccess: () => {
          setCreateOpen(false);
          setName("");
          setDescription("");
          setSelected(new Set());
          setBaseRole("member");
        },
      }
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-4 p-6">
        <div className="space-y-1">
          <h2 className="text-base font-medium">Built-in roles</h2>
          <p className="text-sm text-muted-foreground">
            Each role inherits everything the roles below it can do. These are fixed and
            cannot be edited.
          </p>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Role</TableHead>
              <TableHead>What it can do</TableHead>
              <TableHead className="text-right">Permissions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(builtinRoles ?? []).map((entry) => (
              <TableRow key={entry.role}>
                <TableCell>
                  <StatusBadge tone={entry.role === "owner" ? "brand" : "neutral"}>
                    {entry.role}
                  </StatusBadge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {ROLE_DESCRIPTIONS[entry.role]}
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {entry.permissions.length}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <Card className="flex flex-col gap-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-base font-medium">Custom roles</h2>
            <p className="text-sm text-muted-foreground">
              Start from a built-in role and add permissions on top. A custom role can add
              capabilities but never removes what its base role already grants.
            </p>
          </div>
          {canManage ? (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus aria-hidden="true" />
              New role
            </Button>
          ) : null}
        </div>

        {(customRoles ?? []).length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No custom roles yet"
            description="The seven built-in roles cover most teams. Define a custom role when someone needs one extra capability without a full promotion."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Based on</TableHead>
                <TableHead>Extra permissions</TableHead>
                {canManage ? <TableHead className="sr-only">Actions</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(customRoles ?? []).map((role) => (
                <TableRow key={role.id}>
                  <TableCell>
                    <div className="font-medium">{role.name}</div>
                    {role.description ? (
                      <div className="text-sm text-muted-foreground">{role.description}</div>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone="neutral">{role.base_role}</StatusBadge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {role.permissions.length === 0
                      ? "None — same as its base role"
                      : role.permissions.join(", ")}
                  </TableCell>
                  {canManage ? (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setPendingDelete(role)}
                        disabled={deleteRole.isPending}
                      >
                        <Trash2 aria-hidden="true" />
                        <span className="sr-only">Delete {role.name}</span>
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>New custom role</DialogTitle>
            <DialogDescription>
              Pick the closest built-in role, then add the extra permissions this role needs.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="role-name">Name</Label>
              <Input
                id="role-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Support Engineer"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="role-description">Description</Label>
              <Input
                id="role-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Can read audit logs without full analyst access"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="role-base">Based on</Label>
              <Select value={baseRole} onValueChange={(value) => setBaseRole(value as Role)}>
                <SelectTrigger id="role-base">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(builtinRoles ?? [])
                    .filter((entry) => entry.role !== "owner")
                    .map((entry) => (
                      <SelectItem key={entry.role} value={entry.role}>
                        {entry.role}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <p className="text-sm text-muted-foreground">
                {ROLE_DESCRIPTIONS[baseRole]}
              </p>
            </div>

            <fieldset className="space-y-3">
              <legend className="text-sm font-medium">Extra permissions</legend>
              {[...groupByResource(allPermissions)].map(([resource, permissions]) => (
                <div key={resource} className="space-y-2">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    {formatResource(resource)}
                  </h3>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {permissions.map((permission) => {
                      const isInherited = inherited.has(permission);
                      return (
                        <div key={permission} className="flex items-center gap-2">
                          <Checkbox
                            id={`perm-${permission}`}
                            checked={isInherited || selected.has(permission)}
                            disabled={isInherited}
                            onCheckedChange={() => togglePermission(permission)}
                          />
                          <Label
                            htmlFor={`perm-${permission}`}
                            className="text-sm font-normal"
                          >
                            {permission.split(":")[1]}
                            {isInherited ? (
                              <span className="ml-1 text-muted-foreground">(inherited)</span>
                            ) : null}
                          </Label>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </fieldset>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={!name.trim() || createRole.isPending}>
              {createRole.isPending ? "Creating…" : "Create role"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {pendingDelete?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Anyone holding this role keeps their workspace access and falls back to their
              base role. Nobody is locked out.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                if (pendingDelete) {
                  deleteRole.mutate(pendingDelete.id);
                }
                setPendingDelete(null);
              }}
            >
              Delete role
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
