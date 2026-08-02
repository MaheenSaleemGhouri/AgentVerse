"use client";

import { Monitor } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { authClient } from "@/lib/auth-client";
import { formatRelativeTime } from "@/lib/format";

import { EmptyState } from "@/components/patterns/empty-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface SessionRow {
  id: string;
  token: string;
  createdAt: string | Date;
  ipAddress?: string | null | undefined;
  userAgent?: string | null | undefined;
}

/**
 * Device/session management (Increment 7.3). No new table — Better
 * Auth's existing `sessions` row already carries `ip_address` and
 * `user_agent`, so this is a read of data that was always being
 * recorded, plus its own revoke endpoint.
 */
export function SessionsPanel({
  currentSessionToken,
}: {
  currentSessionToken: string | null;
}): React.JSX.Element {
  const [sessions, setSessions] = React.useState<SessionRow[] | null>(null);
  const [revoking, setRevoking] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    const { data, error } = await authClient.listSessions();
    if (error || !data) {
      toast.error("Could not load your sessions.");
      setSessions([]);
      return;
    }
    setSessions(data as SessionRow[]);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function revoke(token: string): Promise<void> {
    setRevoking(token);
    const { error } = await authClient.revokeSession({ token });
    setRevoking(null);
    if (error) {
      toast.error("Could not sign that device out.");
      return;
    }
    toast.success("Signed that device out.");
    await load();
  }

  return (
    <Card className="gap-4 p-6">
      <div>
        <h2 className="font-medium">Active sessions</h2>
        <p className="text-sm text-muted-foreground">
          Every device currently signed in to your account. Revoking one signs it out
          immediately.
        </p>
      </div>

      {sessions === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : sessions.length === 0 ? (
        <EmptyState
          icon={Monitor}
          title="No other sessions"
          description="You are only signed in on this device."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Device</TableHead>
              <TableHead>IP</TableHead>
              <TableHead>Signed in</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.map((session) => {
              const isCurrent = session.token === currentSessionToken;
              return (
                <TableRow key={session.id}>
                  <TableCell className="max-w-xs">
                    <p className="truncate text-sm">{session.userAgent ?? "Unknown device"}</p>
                    {isCurrent && (
                      <StatusBadge tone="brand" className="mt-1">
                        This device
                      </StatusBadge>
                    )}
                  </TableCell>
                  <TableCell>
                    <code className="font-mono text-xs text-muted-foreground">
                      {session.ipAddress ?? "—"}
                    </code>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(String(session.createdAt))}
                  </TableCell>
                  <TableCell>
                    {/* The current session is deliberately not revocable
                        here — signing yourself out mid-page is a Sign out
                        action, not a device-management one. */}
                    {!isCurrent && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void revoke(session.token)}
                        disabled={revoking === session.token}
                      >
                        {revoking === session.token ? "Revoking…" : "Revoke"}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
