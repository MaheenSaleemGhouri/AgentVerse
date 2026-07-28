"use client";

import { KeyRound, ShieldCheck, Trash2 } from "lucide-react";
import * as React from "react";

import type { AuthScheme, InstalledServer } from "@/lib/api/integrations";
import { formatRelativeTime } from "@/lib/format";
import { useCredentials, useDeleteCredential, usePutCredential } from "@/lib/queries/integrations";

import { EmptyState } from "@/components/patterns/empty-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import { Skeleton } from "@/components/ui/skeleton";

const SCHEMES: ReadonlyArray<{ value: AuthScheme; label: string }> = [
  { value: "api_key", label: "API key" },
  { value: "bearer_token", label: "Bearer token" },
  { value: "basic", label: "Basic auth" },
  { value: "custom_header", label: "Custom header" },
];

/**
 * Credentials for one installed server.
 *
 * There is no reveal control and no copy button, because there is
 * nothing to reveal or copy: the API has no endpoint that returns a
 * credential value. What is shown is which keys exist, when each was
 * last rotated, and the last four characters — enough to answer "is this
 * the one I pasted?" and nothing more.
 */
export function CredentialsPanel({
  workspaceId,
  server,
}: {
  workspaceId: string;
  server: InstalledServer;
}): React.JSX.Element {
  const { data, isLoading } = useCredentials(workspaceId, server.id);
  const put = usePutCredential(workspaceId, server.id);
  const remove = useDeleteCredential(workspaceId, server.id);

  const [key, setKey] = React.useState("");
  const [value, setValue] = React.useState("");
  const [scheme, setScheme] = React.useState<AuthScheme>("api_key");

  function onSave(): void {
    put.mutate(
      { key: key.trim(), value, auth_scheme: scheme },
      {
        onSuccess: () => {
          setKey("");
          // Cleared immediately: the value has been sent and encrypted,
          // and leaving it in a DOM input is a secret sitting in memory
          // and in any screenshot the user takes next.
          setValue("");
        },
      }
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Alert tone="info">
        <ShieldCheck />
        <AlertDescription>
          Credentials are encrypted before they are stored and are resolved only at the moment a
          tool runs. They are never written to logs, never included in an agent&apos;s
          configuration, and cannot be read back — not even by you. To replace one, save a new
          value over it.
        </AlertDescription>
      </Alert>

      {isLoading ? (
        <Skeleton className="h-24 rounded-lg" />
      ) : (data ?? []).length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No credentials stored"
          description={
            server.status === "pending_auth"
              ? "This server needs a credential before agents can use it."
              : "This server does not require a credential."
          }
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {(data ?? []).map((credential) => (
            <li
              key={credential.id}
              className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3"
            >
              <KeyRound className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm">{credential.key}</p>
                <p className="text-xs text-muted-foreground">
                  {credential.hint ? `ends ••••${credential.hint}` : "stored"}
                  {credential.last_rotated_at
                    ? ` · updated ${formatRelativeTime(credential.last_rotated_at)}`
                    : ""}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Delete ${credential.key}`}
                onClick={() => remove.mutate(credential.key)}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Card className="gap-4 p-5">
        <h3 className="text-sm font-medium">
          {(data ?? []).length > 0 ? "Add or replace a credential" : "Add a credential"}
        </h3>

        {server.mcp_server_id !== null && (
          <p className="text-xs text-muted-foreground">
            Use the exact key name this server expects — the marketplace card lists it.
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="credential-key">Key name</Label>
            <Input
              id="credential-key"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              placeholder="GITHUB_PERSONAL_ACCESS_TOKEN"
              autoComplete="off"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="credential-scheme">Type</Label>
            <Select value={scheme} onValueChange={(next) => setScheme(next as AuthScheme)}>
              <SelectTrigger id="credential-scheme">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SCHEMES.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="credential-value">Value</Label>
          <Input
            id="credential-value"
            type="password"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Paste the secret"
            // Password managers should not offer to save a third-party
            // API key as if it were a login for this site.
            autoComplete="off"
            spellCheck={false}
          />
          <p className="text-xs text-muted-foreground">
            You will not be able to view this again after saving.
          </p>
        </div>

        <div className="flex justify-end">
          <Button onClick={onSave} disabled={!key.trim() || !value || put.isPending}>
            {put.isPending ? "Saving…" : "Save credential"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
