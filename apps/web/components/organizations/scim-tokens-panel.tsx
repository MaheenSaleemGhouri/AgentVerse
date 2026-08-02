"use client";

import { Plus, ShieldCheck, Trash2, TriangleAlert } from "lucide-react";
import * as React from "react";

import {
  issueScimTokenAction,
  revokeScimTokenAction,
} from "@/lib/api/actions";
import type { IssuedScimToken, ScimToken } from "@/lib/api/scim-tokens";
import { formatRelativeTime } from "@/lib/format";

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

/**
 * SCIM token management, mirroring `settings/api-keys-panel.tsx` rather
 * than inventing a second shape for "issue a secret, show it once,
 * revoke it later" — the same interaction, so the same pattern.
 */
export function ScimTokensPanel({
  organizationId,
  scimBaseUrl,
  initialTokens,
}: {
  organizationId: string;
  /** `null` when the deployment has not published a public API origin —
   *  see `lib/scim.ts` for why a placeholder is worse than none. */
  scimBaseUrl: string | null;
  initialTokens: ScimToken[];
}): React.JSX.Element {
  const [tokens, setTokens] = React.useState<ScimToken[]>(initialTokens);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [issued, setIssued] = React.useState<IssuedScimToken | null>(null);
  const [pendingRevoke, setPendingRevoke] = React.useState<ScimToken | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function createToken(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const result = await issueScimTokenAction(organizationId, name.trim());
      setIssued(result);
      setTokens((current) => [...current, result]);
      setCreateOpen(false);
      setName("");
    } catch {
      setError("Could not issue the token. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeToken(token: ScimToken): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await revokeScimTokenAction(organizationId, token.id);
      setTokens((current) =>
        current.map((t) =>
          t.id === token.id ? { ...t, revoked_at: new Date().toISOString() } : t
        )
      );
    } catch {
      setError("Could not revoke the token. Try again.");
    } finally {
      setBusy(false);
      setPendingRevoke(null);
    }
  }

  return (
    <Card className="flex flex-col gap-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-base font-medium">Directory sync (SCIM 2.0)</h2>
          <p className="text-sm text-muted-foreground">
            Let your identity provider create and deactivate this organization&rsquo;s people
            automatically. Point it at the base URL below and give it a token.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus aria-hidden="true" />
          New token
        </Button>
      </div>

      <div className="space-y-2">
        <Label htmlFor="scim-base-url">SCIM base URL</Label>
        {scimBaseUrl ? (
          <div className="flex items-center gap-2">
            <Input id="scim-base-url" readOnly value={scimBaseUrl} className="font-mono text-xs" />
            <CopyButton value={scimBaseUrl} label="Copy SCIM base URL" />
          </div>
        ) : (
          <p id="scim-base-url" className="text-sm text-muted-foreground">
            This deployment has no public API URL configured (<code>API_PUBLIC_URL</code>), so the
            base URL cannot be shown here. Your platform administrator has it; tokens issued below
            work regardless.
          </p>
        )}
      </div>

      <Alert>
        <ShieldCheck aria-hidden="true" />
        <AlertTitle>Users sync; groups do not</AlertTitle>
        <AlertDescription>
          SCIM provisions organization membership only. Workspace access is granted separately in
          AgentVerse, so push-groups is intentionally unsupported and your provider will report it
          as not implemented.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert tone="danger">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {tokens.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No SCIM tokens yet"
          description="Issue a token, then paste it into your identity provider's provisioning settings."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Token</TableHead>
              <TableHead>Last used</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="sr-only">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tokens.map((token) => (
              <TableRow key={token.id}>
                <TableCell>{token.name}</TableCell>
                <TableCell className="font-mono text-xs">{token.token_prefix}…</TableCell>
                <TableCell className="text-muted-foreground">
                  {token.last_used_at ? formatRelativeTime(token.last_used_at) : "Never"}
                </TableCell>
                <TableCell>
                  <StatusBadge tone={token.revoked_at ? "danger" : "success"}>
                    {token.revoked_at ? "Revoked" : "Active"}
                  </StatusBadge>
                </TableCell>
                <TableCell className="text-right">
                  {token.revoked_at ? null : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setPendingRevoke(token)}
                      disabled={busy}
                    >
                      <Trash2 aria-hidden="true" />
                      <span className="sr-only">Revoke {token.name}</span>
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New SCIM token</DialogTitle>
            <DialogDescription>
              Name it after the provider that will use it, so you can tell tokens apart later.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="scim-token-name">Name</Label>
            <Input
              id="scim-token-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Okta production"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={createToken} disabled={!name.trim() || busy}>
              {busy ? "Issuing…" : "Issue token"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={issued !== null} onOpenChange={(open) => !open && setIssued(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your SCIM token now</DialogTitle>
            <DialogDescription>
              This is the only time it is shown. If you lose it, revoke this token and issue a
              new one.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2">
            <Input readOnly value={issued?.token ?? ""} className="font-mono text-xs" />
            <CopyButton value={issued?.token ?? ""} label="Copy SCIM token" />
          </div>
          <DialogFooter>
            <Button onClick={() => setIssued(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke {pendingRevoke?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Your identity provider will stop being able to sync members immediately. Existing
              members keep their access — only provisioning stops.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => pendingRevoke && revokeToken(pendingRevoke)}
            >
              Revoke token
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
