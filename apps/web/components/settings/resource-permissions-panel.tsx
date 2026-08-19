"use client";

import { Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import type { ResourcePermission } from "@/lib/api/resource-permissions";
import { formatRelativeTime } from "@/lib/format";
import {
  useGrantResourcePermission,
  useResourcePermissions,
  useRevokeResourcePermission,
} from "@/lib/queries/resource-permissions";

import { EmptyState } from "@/components/patterns/empty-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/**
 * Orthogonal to the four workspace roles (Increment 6) — grants a
 * specific person one named permission on one resource type without
 * changing their `owner/admin/member/viewer` role at all. Not yet
 * enforced by any route outside `require_resource_permission`'s own
 * composition contract; no product route composes it yet, so a grant
 * made here has no visible effect until one does — stated plainly
 * rather than implying otherwise.
 */
export function ResourcePermissionsPanel({
  workspaceId,
  initialGrants,
}: {
  workspaceId: string;
  initialGrants: ResourcePermission[];
}): React.JSX.Element {
  const { data: grants } = useResourcePermissions(workspaceId, initialGrants);
  const grant = useGrantResourcePermission(workspaceId);
  const revoke = useRevokeResourcePermission(workspaceId);
  const searchParams = useSearchParams();
  const prefillType = searchParams.get("resourceType") ?? "";
  const prefillId = searchParams.get("resourceId") ?? "";

  // A deep link (e.g. the workflow builder's "Share" button) opens the
  // grant dialog pre-filled rather than requiring the resource type/id
  // to be typed by hand — the URL is the whole hand-off, no new backend
  // call needed since `resource_type` is already unrestricted free text.
  const [open, setOpen] = React.useState(Boolean(prefillType));
  const [resourceType, setResourceType] = React.useState(prefillType);
  const [resourceId, setResourceId] = React.useState(prefillId);
  const [principalId, setPrincipalId] = React.useState("");
  const [permission, setPermission] = React.useState("");

  const canSubmit = resourceType.trim() && principalId.trim() && permission.trim();

  function submit(): void {
    if (!canSubmit) return;
    grant.mutate(
      {
        resource_type: resourceType.trim(),
        resource_id: resourceId.trim(),
        principal_id: principalId.trim(),
        permission: permission.trim(),
      },
      {
        onSuccess: () => {
          setOpen(false);
          setResourceType("");
          setResourceId("");
          setPrincipalId("");
          setPermission("");
        },
      }
    );
  }

  return (
    <div id="resource-permissions" className="space-y-4 scroll-mt-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-medium">Resource permissions</h2>
          <p className="text-sm text-muted-foreground">
            Grant a specific permission on a resource type to one person, independent of their
            workspace role.
          </p>
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}>
          <Plus />
          Grant permission
        </Button>
      </div>

      {(grants ?? []).length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No resource permissions granted"
          description="Everyone's access is determined entirely by their workspace role."
        />
      ) : (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Resource</TableHead>
                <TableHead>Permission</TableHead>
                <TableHead>Principal</TableHead>
                <TableHead>Granted</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(grants ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <code className="font-mono text-xs">
                      {row.resource_type}
                      {row.resource_id ? `:${row.resource_id}` : ""}
                    </code>
                    {!row.resource_id && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Every resource of this type
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone="brand">{row.permission}</StatusBadge>
                  </TableCell>
                  <TableCell>
                    <code className="font-mono text-xs text-muted-foreground">
                      {row.principal_id}
                    </code>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(row.created_at)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Revoke ${row.permission} on ${row.resource_type}`}
                      onClick={() => revoke.mutate(row.id)}
                      disabled={revoke.isPending}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Grant a resource permission</DialogTitle>
            <DialogDescription>
              This adds a specific permission on top of the person&apos;s existing role — it
              never lowers it.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rp-resource-type">Resource type</Label>
            <Input
              id="rp-resource-type"
              value={resourceType}
              onChange={(event) => setResourceType(event.target.value)}
              placeholder="billing"
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rp-resource-id">Resource ID</Label>
            <Input
              id="rp-resource-id"
              value={resourceId}
              onChange={(event) => setResourceId(event.target.value)}
              placeholder="Leave blank for every resource of this type"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rp-permission">Permission</Label>
            <Input
              id="rp-permission"
              value={permission}
              onChange={(event) => setPermission(event.target.value)}
              placeholder="manage"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rp-principal">User ID</Label>
            <Input
              id="rp-principal"
              value={principalId}
              onChange={(event) => setPrincipalId(event.target.value)}
              placeholder="usr_…"
              className="font-mono"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={!canSubmit || grant.isPending}>
              {grant.isPending ? "Granting…" : "Grant"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
