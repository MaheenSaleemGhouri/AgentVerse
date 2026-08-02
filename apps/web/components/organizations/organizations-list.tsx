"use client";

import { Building2, Plus } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Organization } from "@/lib/api/organizations";
import { formatRelativeTime, initialsFrom } from "@/lib/format";
import { useCreateOrganization, useMyOrganizations } from "@/lib/queries/organizations";

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

export function OrganizationsList({
  initialOrganizations,
}: {
  initialOrganizations: Organization[];
}): React.JSX.Element {
  const { data: organizations } = useMyOrganizations(initialOrganizations);
  const createOrganization = useCreateOrganization();
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");

  function create(): void {
    if (!name.trim()) return;
    createOrganization.mutate(name.trim(), {
      onSuccess: () => {
        setOpen(false);
        setName("");
      },
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button onClick={() => setOpen(true)}>
          <Plus />
          New organization
        </Button>
      </div>

      {(organizations ?? []).length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No organizations yet"
          description="Create one to group workspaces under shared billing, SSO, and branding."
          action={
            <Button onClick={() => setOpen(true)}>
              <Plus />
              New organization
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {(organizations ?? []).map((organization) => (
            <Link key={organization.id} href={`/organizations/${organization.id}/settings`}>
              <Card className="gap-3 p-4 transition-colors hover:border-primary/40">
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-xs font-semibold text-primary-foreground"
                  >
                    {initialsFrom(organization.name)}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{organization.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      Created {formatRelativeTime(organization.created_at)}
                    </p>
                  </div>
                  <StatusBadge
                    tone={organization.role === "owner" ? "brand" : "neutral"}
                    className="ml-auto"
                  >
                    <span className="capitalize">{organization.role}</span>
                  </StatusBadge>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New organization</DialogTitle>
            <DialogDescription>
              You become its owner. It starts with no workspaces attached.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="org-name">Name</Label>
            <Input
              id="org-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && create()}
              placeholder="Acme Inc."
              autoFocus
              maxLength={200}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={create} disabled={!name.trim() || createOrganization.isPending}>
              {createOrganization.isPending ? "Creating…" : "Create organization"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
