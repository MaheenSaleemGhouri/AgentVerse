"use client";

import { KeyRound, Plus, Trash2, TriangleAlert } from "lucide-react";
import * as React from "react";

import type { ApiKey } from "@/lib/api/workspaces";
import { formatRelativeTime } from "@/lib/format";
import { useApiKeys, useIssueApiKey, useRevokeApiKey } from "@/lib/queries/workspace";
import { cn } from "@/lib/utils";

import { CopyButton } from "@/components/patterns/copy-button";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
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

export function ApiKeysPanel({
  workspaceId,
  initialKeys,
}: {
  workspaceId: string;
  initialKeys: ApiKey[];
}): React.JSX.Element {
  const { data: keys } = useApiKeys(workspaceId, initialKeys);
  const issueKey = useIssueApiKey(workspaceId);
  const revokeKey = useRevokeApiKey(workspaceId);

  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  // Held in component state only, never written to the query cache —
  // the plaintext key is returned exactly once and must not be
  // retrievable from anywhere afterwards.
  const [issuedSecret, setIssuedSecret] = React.useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = React.useState<ApiKey | null>(null);

  function createKey(): void {
    if (!name.trim()) return;
    issueKey.mutate(name.trim(), {
      onSuccess: (issued) => {
        setCreateOpen(false);
        setName("");
        setIssuedSecret(issued.key);
      },
    });
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-medium">API keys</h2>
          <p className="text-sm text-muted-foreground">
            Workspace-scoped keys for calling the AgentVerse API programmatically.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus />
          New key
        </Button>
      </div>

      <Alert tone="info">
        <KeyRound />
        <AlertTitle>Keys are shown once</AlertTitle>
        <AlertDescription>
          Only a hash is stored, so a key cannot be recovered after you close the dialog. Lost a
          key? Revoke it and issue a new one.
        </AlertDescription>
      </Alert>

      {(keys ?? []).length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No API keys yet"
          description="Issue a key to call the API from a script, a CI job, or your own backend."
          action={
            <Button onClick={() => setCreateOpen(true)}>
              <Plus />
              Issue a key
            </Button>
          }
        />
      ) : (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(keys ?? []).map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell>
                    <code className="font-mono text-xs text-muted-foreground">
                      {key.key_prefix}…
                    </code>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(key.created_at)}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {/* "Never used" is a real signal — an unused key is
                        usually a leftover worth revoking. */}
                    {key.last_used_at ? formatRelativeTime(key.last_used_at) : "Never"}
                  </TableCell>
                  <TableCell>
                    {key.revoked_at ? (
                      <StatusBadge tone="danger">Revoked</StatusBadge>
                    ) : (
                      <StatusBadge tone="success">Active</StatusBadge>
                    )}
                  </TableCell>
                  <TableCell>
                    {!key.revoked_at && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Revoke ${key.name}`}
                        onClick={() => setPendingRevoke(key)}
                      >
                        <Trash2 />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New API key</DialogTitle>
            <DialogDescription>
              Name it after where it will be used, so you know what breaks if you revoke it.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="key-name">Name</Label>
            <Input
              id="key-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && createKey()}
              placeholder="CI pipeline"
              autoFocus
              maxLength={100}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={createKey} disabled={!name.trim() || issueKey.isPending}>
              {issueKey.isPending ? "Issuing…" : "Issue key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={issuedSecret !== null}
        // Closing is the only exit — there is deliberately no way back
        // to this value once dismissed.
        onOpenChange={(open) => !open && setIssuedSecret(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your key now</DialogTitle>
            <DialogDescription>
              This is the only time it will be shown. Store it somewhere safe before closing.
            </DialogDescription>
          </DialogHeader>
          <Alert tone="warning">
            <TriangleAlert />
            <AlertTitle>Treat this like a password</AlertTitle>
            <AlertDescription>
              It grants API access to this workspace. Never commit it or paste it into a client
              bundle.
            </AlertDescription>
          </Alert>
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted p-3">
            <code className="min-w-0 flex-1 font-mono text-xs break-all">{issuedSecret}</code>
            {issuedSecret && <CopyButton value={issuedSecret} label="Copy API key" />}
          </div>
          <DialogFooter>
            <Button onClick={() => setIssuedSecret(null)}>I&apos;ve saved it</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke “{pendingRevoke?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Every request using this key starts failing immediately. This cannot be undone —
              you would need to issue a new key and update whatever was using it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() => {
                if (pendingRevoke) revokeKey.mutate(pendingRevoke.id);
                setPendingRevoke(null);
              }}
            >
              Revoke key
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
