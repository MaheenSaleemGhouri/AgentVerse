"use client";

import { Plug, Plus, Trash2, TriangleAlert } from "lucide-react";
import * as React from "react";

import type { ApiKeyScope, McpClient } from "@/lib/api/workspaces";
import { formatRelativeTime } from "@/lib/format";
import { useIssueMcpClient, useMcpClients, useRevokeMcpClient } from "@/lib/queries/workspace";
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

function isExpired(expiresAt: string | null): boolean {
  return expiresAt !== null && new Date(expiresAt).getTime() <= Date.now();
}

const SCOPE_LABEL: Record<ApiKeyScope, string> = {
  full: "Full access",
  read_only: "Read-only",
};

export function McpClientsPanel({
  workspaceId,
  initialClients,
}: {
  workspaceId: string;
  initialClients: McpClient[];
}): React.JSX.Element {
  const { data: clients } = useMcpClients(workspaceId, initialClients);
  const issueClient = useIssueMcpClient(workspaceId);
  const revokeClient = useRevokeMcpClient(workspaceId);

  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [scope, setScope] = React.useState<ApiKeyScope>("full");
  const [expiry, setExpiry] = React.useState<string>("90");
  // Held in component state only, never written to the query cache — the
  // plaintext credential is returned exactly once and must not be
  // retrievable from anywhere afterwards.
  const [issuedSecret, setIssuedSecret] = React.useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = React.useState<McpClient | null>(null);

  function createClient(): void {
    if (!name.trim()) return;
    issueClient.mutate(
      {
        name: name.trim(),
        scope,
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

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-medium">MCP clients</h2>
          <p className="text-sm text-muted-foreground">
            Credentials for external MCP clients (Claude Desktop, another agent) connecting to
            AgentVerse&apos;s own MCP server. Separate from API keys — an MCP integration token
            leaking does not hand out REST API access, and vice versa.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus />
          New client
        </Button>
      </div>

      <Alert tone="info">
        <Plug />
        <AlertTitle>Credentials are shown once</AlertTitle>
        <AlertDescription>
          Only a hash is stored, so a credential cannot be recovered after you close the dialog.
          Lost one? Revoke it and issue a new one.
        </AlertDescription>
      </Alert>

      {(clients ?? []).length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No MCP clients yet"
          description="Issue a credential to connect an external MCP client to this workspace's agents and workflows."
          action={
            <Button onClick={() => setCreateOpen(true)}>
              <Plus />
              Issue a client credential
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
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(clients ?? []).map((client) => (
                <TableRow key={client.id}>
                  <TableCell className="font-medium">{client.name}</TableCell>
                  <TableCell>
                    <code className="font-mono text-xs text-muted-foreground">
                      {client.key_prefix}…
                    </code>
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone={client.scope === "full" ? "brand" : "neutral"}>
                      {SCOPE_LABEL[client.scope]}
                    </StatusBadge>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(client.created_at)}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {client.last_used_at ? formatRelativeTime(client.last_used_at) : "Never"}
                    {client.use_count > 0 && (
                      <p className="text-xs">
                        {client.use_count.toLocaleString()} call
                        {client.use_count === 1 ? "" : "s"}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {client.expires_at ? formatRelativeTime(client.expires_at) : "Never"}
                  </TableCell>
                  <TableCell>
                    {client.revoked_at ? (
                      <StatusBadge tone="danger">Revoked</StatusBadge>
                    ) : isExpired(client.expires_at) ? (
                      <StatusBadge tone="warning">Expired</StatusBadge>
                    ) : (
                      <StatusBadge tone="success">Active</StatusBadge>
                    )}
                  </TableCell>
                  <TableCell>
                    {!client.revoked_at && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Revoke ${client.name}`}
                        onClick={() => setPendingRevoke(client)}
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
            <DialogTitle>New MCP client</DialogTitle>
            <DialogDescription>
              Name it after the client that will use it, so you know what breaks if you revoke
              it.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="mcp-client-name">Name</Label>
            <Input
              id="mcp-client-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && createClient()}
              placeholder="Claude Desktop"
              autoFocus
              maxLength={200}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-client-scope">Scope</Label>
            <Select value={scope} onValueChange={(value) => setScope(value as ApiKeyScope)}>
              <SelectTrigger id="mcp-client-scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full">Full access</SelectItem>
                <SelectItem value="read_only">Read-only</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Read-only caps every tool call at viewer — list and get tools only.{" "}
              <code className="font-mono">run_agent</code>/<code className="font-mono">
                run_workflow
              </code>{" "}
              are refused.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-client-expiry">Expires</Label>
            <Select value={expiry} onValueChange={setExpiry}>
              <SelectTrigger id="mcp-client-expiry">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">In 30 days</SelectItem>
                <SelectItem value="90">In 90 days</SelectItem>
                <SelectItem value="365">In a year</SelectItem>
                <SelectItem value="never">Never</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={createClient} disabled={!name.trim() || issueClient.isPending}>
              {issueClient.isPending ? "Issuing…" : "Issue credential"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={issuedSecret !== null}
        onOpenChange={(open) => !open && setIssuedSecret(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your credential now</DialogTitle>
            <DialogDescription>
              This is the only time it will be shown. Paste it into the connecting MCP
              client&apos;s configuration before closing.
            </DialogDescription>
          </DialogHeader>
          <Alert tone="warning">
            <TriangleAlert />
            <AlertTitle>Treat this like a password</AlertTitle>
            <AlertDescription>
              It grants MCP access to this workspace&apos;s agents and workflows at the scope you
              chose. Never commit it or paste it into a client bundle.
            </AlertDescription>
          </Alert>
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted p-3">
            <code className="min-w-0 flex-1 font-mono text-xs break-all">{issuedSecret}</code>
            {issuedSecret && <CopyButton value={issuedSecret} label="Copy MCP client credential" />}
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
              The connected MCP client starts failing immediately. This cannot be undone — you
              would need to issue a new credential and reconfigure the client.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={cn(buttonVariants({ variant: "destructive" }))}
              onClick={() => {
                if (pendingRevoke) revokeClient.mutate(pendingRevoke.id);
                setPendingRevoke(null);
              }}
            >
              Revoke client
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
