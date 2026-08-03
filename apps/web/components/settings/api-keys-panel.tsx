"use client";

import { KeyRound, Plus, RotateCw, Trash2, TriangleAlert } from "lucide-react";
import * as React from "react";

import type { ApiKey, ApiKeyScope } from "@/lib/api/workspaces";
import { formatRelativeTime } from "@/lib/format";
import {
  useApiKeys,
  useIssueApiKey,
  useRevokeApiKey,
  useRotateApiKey,
} from "@/lib/queries/workspace";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** The server refuses an expired key regardless; this only decides how
 *  the row is labelled, so a clock skew of seconds is harmless here. */
function isExpired(expiresAt: string | null): boolean {
  return expiresAt !== null && new Date(expiresAt).getTime() <= Date.now();
}

const SCOPE_LABEL: Record<ApiKeyScope, string> = {
  full: "Full access",
  read_only: "Read-only",
};

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
  const rotateKey = useRotateApiKey(workspaceId);

  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [scope, setScope] = React.useState<ApiKeyScope>("full");
  // "never" is a deliberate option rather than the absence of a choice:
  // it is what every key issued before expiry shipped already does, and
  // making it explicit means the person issuing one has to mean it.
  const [expiry, setExpiry] = React.useState<string>("90");
  // Held in component state only, never written to the query cache —
  // the plaintext key is returned exactly once and must not be
  // retrievable from anywhere afterwards.
  const [issuedSecret, setIssuedSecret] = React.useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = React.useState<ApiKey | null>(null);

  function createKey(): void {
    if (!name.trim()) return;
    issueKey.mutate(
      // `tier` has no picker yet — "standard" is the only tier that
      // exists today, sent explicitly since the generated request type
      // treats every field with a schema default as required to send.
      {
        name: name.trim(),
        scope,
        tier: "standard",
        expires_in_days: expiry === "never" ? null : Number(expiry),
      },
      {
        onSuccess: (issued) => {
          setCreateOpen(false);
          setName("");
          setScope("full");
          setExpiry("90");
          setIssuedSecret(issued.key);
        },
      }
    );
  }

  function rotate(key: ApiKey): void {
    rotateKey.mutate(key.id, {
      onSuccess: (issued) => setIssuedSecret(issued.key),
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
                <TableHead>Scope</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24" />
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
                    {key.rotated_from_id && (
                      <p className="mt-0.5 text-xs text-muted-foreground">Rotated key</p>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone={key.scope === "full" ? "brand" : "neutral"}>
                      {SCOPE_LABEL[key.scope]}
                    </StatusBadge>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(key.created_at)}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {/* "Never used" is a real signal — an unused key is
                        usually a leftover worth revoking. The call count
                        answers the follow-up question a bare timestamp
                        cannot: is it still carrying real traffic? */}
                    {key.last_used_at ? formatRelativeTime(key.last_used_at) : "Never"}
                    {key.use_count > 0 && (
                      <p className="text-xs">
                        {key.use_count.toLocaleString()} call
                        {key.use_count === 1 ? "" : "s"}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {key.expires_at ? formatRelativeTime(key.expires_at) : "Never"}
                  </TableCell>
                  <TableCell>
                    {key.revoked_at ? (
                      <StatusBadge tone="danger">Revoked</StatusBadge>
                    ) : isExpired(key.expires_at) ? (
                      // Distinct from Revoked: nobody revoked it, its
                      // configured lifetime simply ran out. Both stop
                      // authenticating; only one was a decision.
                      <StatusBadge tone="warning">Expired</StatusBadge>
                    ) : (
                      <StatusBadge tone="success">Active</StatusBadge>
                    )}
                  </TableCell>
                  <TableCell>
                    {!key.revoked_at && (
                      <div className="flex items-center gap-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Rotate ${key.name}`}
                              onClick={() => rotate(key)}
                              disabled={rotateKey.isPending}
                            >
                              <RotateCw />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            Revokes this key and issues a replacement with the same name and
                            scope
                          </TooltipContent>
                        </Tooltip>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Revoke ${key.name}`}
                          onClick={() => setPendingRevoke(key)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
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
          <div className="space-y-2">
            <Label htmlFor="key-scope">Scope</Label>
            <Select value={scope} onValueChange={(value) => setScope(value as ApiKeyScope)}>
              <SelectTrigger id="key-scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full">Full access</SelectItem>
                <SelectItem value="read_only">Read-only</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Read-only keys are capped at viewer access. A key never grants more than
              the member who issued it currently has.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="key-expiry">Expires</Label>
            <Select value={expiry} onValueChange={setExpiry}>
              <SelectTrigger id="key-expiry">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">In 30 days</SelectItem>
                <SelectItem value="90">In 90 days</SelectItem>
                <SelectItem value="365">In a year</SelectItem>
                <SelectItem value="never">Never</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              An expired key stops authenticating immediately. Keys that never expire count
              against this workspace&apos;s security score.
            </p>
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
