"use client";

import { Building2, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import * as React from "react";

import type { Organization, OrganizationWorkspace } from "@/lib/api/organizations";
import type { Workspace } from "@/lib/api/workspaces";
import { ROLE_ORDER } from "@/lib/roles";
import {
  useAttachWorkspace,
  useDeleteOrganization,
  useDetachWorkspace,
  useOrgWorkspaces,
  useRenameOrganization,
} from "@/lib/queries/organizations";

import { EmptyState } from "@/components/patterns/empty-state";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export function OrganizationSettingsPanel({
  organization,
  initialAttachedWorkspaces,
  ownedWorkspaces,
}: {
  organization: Organization;
  initialAttachedWorkspaces: OrganizationWorkspace[];
  ownedWorkspaces: Workspace[];
}): React.JSX.Element {
  const router = useRouter();
  const canManage = ROLE_ORDER[organization.role] >= ROLE_ORDER.admin;
  const canDelete = organization.role === "owner";

  const { data: attached } = useOrgWorkspaces(organization.id, initialAttachedWorkspaces);
  const renameOrg = useRenameOrganization(organization.id);
  const deleteOrg = useDeleteOrganization();
  const attachWorkspace = useAttachWorkspace(organization.id);
  const detachWorkspace = useDetachWorkspace(organization.id);

  const [name, setName] = React.useState(organization.name);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [pickedWorkspaceId, setPickedWorkspaceId] = React.useState<string>("");

  const attachedIds = new Set((attached ?? []).map((workspace) => workspace.id));
  const attachable = ownedWorkspaces.filter((workspace) => !attachedIds.has(workspace.id));

  return (
    <div className="flex flex-col gap-6">
      <Card className="p-6">
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="org-name">Name</Label>
            <Input
              id="org-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={!canManage}
              maxLength={200}
            />
          </div>
          <div className="flex justify-end">
            <Button
              onClick={() => renameOrg.mutate(name.trim())}
              disabled={
                !canManage ||
                !name.trim() ||
                name.trim() === organization.name ||
                renameOrg.isPending
              }
            >
              {renameOrg.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </Card>

      <Card className="gap-4 p-6">
        <div>
          <h2 className="font-medium">Attached workspaces</h2>
          <p className="text-sm text-muted-foreground">
            Grouped for billing/SSO/branding only — attaching never grants access. Only
            workspaces you own can be attached or detached.
          </p>
        </div>

        {(attached ?? []).length === 0 ? (
          <EmptyState
            icon={Building2}
            title="No workspaces attached"
            description="Attach a workspace you own below."
          />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {(attached ?? []).map((workspace) => (
              <li key={workspace.id} className="flex items-center justify-between px-4 py-3">
                <Link
                  href={`/dashboard/${workspace.id}`}
                  className="text-sm font-medium hover:underline"
                >
                  {workspace.name}
                </Link>
                {canManage && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => detachWorkspace.mutate(workspace.id)}
                    disabled={detachWorkspace.isPending}
                  >
                    Detach
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        {canManage && attachable.length > 0 && (
          <div className="flex items-center gap-2">
            <Select value={pickedWorkspaceId} onValueChange={setPickedWorkspaceId}>
              <SelectTrigger className="flex-1">
                <SelectValue placeholder="Choose a workspace you own…" />
              </SelectTrigger>
              <SelectContent>
                {attachable.map((workspace) => (
                  <SelectItem key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              disabled={!pickedWorkspaceId || attachWorkspace.isPending}
              onClick={() => {
                attachWorkspace.mutate(pickedWorkspaceId);
                setPickedWorkspaceId("");
              }}
            >
              Attach
            </Button>
          </div>
        )}
      </Card>

      {canDelete && (
        <Card className="gap-3 border-destructive/30 p-6">
          <div>
            <h2 className="font-medium">Delete organization</h2>
            <p className="text-sm text-muted-foreground">
              Attached workspaces are detached, not deleted — nothing in them is affected.
            </p>
          </div>
          <div>
            <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2 />
              Delete organization
            </Button>
          </div>
        </Card>
      )}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{organization.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Its attached workspaces survive with nothing lost — they are only detached. This
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() => {
                deleteOrg.mutate(organization.id, {
                  onSuccess: () => router.push("/organizations"),
                });
                setConfirmDelete(false);
              }}
            >
              Delete organization
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
