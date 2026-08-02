"use client";

import { Globe, Plus, Trash2 } from "lucide-react";
import * as React from "react";

import type { IpAllowlistEntry } from "@/lib/api/ip-allowlist";
import { formatRelativeTime } from "@/lib/format";
import {
  useAddIpAllowlistEntry,
  useIpAllowlist,
  useRemoveIpAllowlistEntry,
} from "@/lib/queries/ip-allowlist";

import { EmptyState } from "@/components/patterns/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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

/** Opt-in IP restriction (Increment 7.4). Empty = unrestricted. */
export function IpAllowlistPanel({
  workspaceId,
  initialEntries,
}: {
  workspaceId: string;
  initialEntries: IpAllowlistEntry[];
}): React.JSX.Element {
  const { data: entries } = useIpAllowlist(workspaceId, initialEntries);
  const addEntry = useAddIpAllowlistEntry(workspaceId);
  const removeEntry = useRemoveIpAllowlistEntry(workspaceId);

  const [open, setOpen] = React.useState(false);
  const [cidr, setCidr] = React.useState("");
  const [label, setLabel] = React.useState("");

  const isRestricted = (entries ?? []).length > 0;

  function submit(): void {
    if (!cidr.trim()) return;
    addEntry.mutate(
      { cidr: cidr.trim(), label: label.trim() || null },
      {
        onSuccess: () => {
          setOpen(false);
          setCidr("");
          setLabel("");
        },
      }
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-medium">IP restrictions</h2>
          <p className="text-sm text-muted-foreground">
            Limit which networks can reach this workspace. With no ranges listed, every IP is
            allowed.
          </p>
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}>
          <Plus />
          Add range
        </Button>
      </div>

      {isRestricted && (
        <Alert tone="warning">
          <Globe />
          <AlertTitle>This workspace is IP-restricted</AlertTitle>
          <AlertDescription>
            Only the ranges below can reach it. This settings page itself always stays
            reachable, so a mistake here can be undone from anywhere.
          </AlertDescription>
        </Alert>
      )}

      {!isRestricted ? (
        <EmptyState
          icon={Globe}
          title="No IP restrictions"
          description="This workspace is reachable from any network. Add a range to restrict it."
        />
      ) : (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Range</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(entries ?? []).map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <code className="font-mono text-xs">{entry.cidr}</code>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {entry.label ?? "—"}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(entry.created_at)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove ${entry.cidr}`}
                      onClick={() => removeEntry.mutate(entry.id)}
                      disabled={removeEntry.isPending}
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
            <DialogTitle>Add an allowed range</DialogTitle>
            <DialogDescription>
              Adding the first range restricts this workspace to it. Make sure it covers your
              own network.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="ip-cidr">IP address or CIDR range</Label>
            <Input
              id="ip-cidr"
              value={cidr}
              onChange={(event) => setCidr(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && submit()}
              placeholder="203.0.113.0/24"
              className="font-mono"
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ip-label">Label</Label>
            <Input
              id="ip-label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Head office VPN"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={!cidr.trim() || addEntry.isPending}>
              {addEntry.isPending ? "Adding…" : "Add range"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
