import { KeyRound, Lock, ShieldCheck } from "lucide-react";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { listAuditLogs } from "@/lib/api/audit-logs";
import { listIpAllowlist } from "@/lib/api/ip-allowlist";
import { listApiKeys, listMyWorkspaces } from "@/lib/api/workspaces";
import { auth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { ROLE_DESCRIPTIONS } from "@/lib/roles";

import { StatusBadge } from "@/components/patterns/status-badge";
import { IpAllowlistPanel } from "@/components/settings/ip-allowlist-panel";
import { SessionsPanel } from "@/components/settings/sessions-panel";
import { TwoFactorPanel } from "@/components/settings/two-factor-panel";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/**
 * Security posture for this workspace and session.
 *
 * Everything shown is derived from real state — the live session, actual
 * issued keys, the caller's real role, and (for admins/owners) real
 * recent audit events.
 */
export default async function SecurityPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");

  const [workspaces, keys] = await Promise.all([listMyWorkspaces(), listApiKeys(workspaceId)]);
  const current = workspaces.find((workspace) => workspace.id === workspaceId);
  if (!current) notFound();

  const activeKeys = keys.filter((key) => !key.revoked_at);
  const staleKeys = activeKeys.filter((key) => key.last_used_at === null);

  // The read route is admin-gated (audit visibility sits above ordinary
  // workspace reads), so a member/viewer never issues this call — a
  // 403 here would be the wrong failure mode for a page every role
  // otherwise sees.
  const canViewAuditTrail = current.role === "owner" || current.role === "admin";
  const recentEvents = canViewAuditTrail
    ? (await listAuditLogs(workspaceId, { limit: 5 })).data
    : [];

  // Admin-gated on the API too, so members/viewers never issue the call.
  const ipAllowlist = canViewAuditTrail ? await listIpAllowlist(workspaceId) : [];

  // `twoFactorEnabled` comes from the live session's user record — the
  // column the `twoFactor()` plugin maintains (Increment 7.2).
  const twoFactorEnabled =
    (session.user as { twoFactorEnabled?: boolean | null }).twoFactorEnabled === true;

  return (
    <div className="max-w-3xl space-y-6">
      <Card className="gap-4 p-6">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-success-soft text-success">
            <Lock className="size-4.5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="font-medium">Session</h2>
            <p className="text-sm text-muted-foreground">
              Your session token is an httpOnly, Secure cookie — it is never readable by JavaScript
              and never stored in localStorage.
            </p>
          </div>
        </div>
        <Separator />
        <Row label="Signed in as" value={session.user.email} />
        <Row label="Session expires" value={formatDateTime(String(session.session.expiresAt))} />
      </Card>

      <TwoFactorPanel enabled={twoFactorEnabled} />

      <SessionsPanel currentSessionToken={session.session.token} />

      <Card className="gap-4 p-6">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <ShieldCheck className="size-4.5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="font-medium">Access control</h2>
            <p className="text-sm text-muted-foreground">
              Permissions are deny-by-default and re-checked server-side on every request.
            </p>
          </div>
        </div>
        <Separator />
        <div className="flex items-start gap-3">
          <StatusBadge tone={current.role === "owner" ? "brand" : "info"}>
            <span className="capitalize">{current.role}</span>
          </StatusBadge>
          <p className="text-sm text-muted-foreground">{ROLE_DESCRIPTIONS[current.role]}</p>
        </div>
      </Card>

      <Card className="gap-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <KeyRound className="size-4.5" aria-hidden="true" />
            </span>
            <div>
              <h2 className="font-medium">API credentials</h2>
              <p className="text-sm text-muted-foreground">
                {activeKeys.length} active key{activeKeys.length === 1 ? "" : "s"} for this
                workspace.
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link href={`/dashboard/${workspaceId}/settings/api-keys`}>Manage</Link>
          </Button>
        </div>

        {staleKeys.length > 0 && (
          <>
            <Separator />
            {/* A never-used key is usually a forgotten one, and every
                un-revoked key is standing attack surface. */}
            <p className="text-sm text-warning">
              {staleKeys.length} active key{staleKeys.length === 1 ? " has" : "s have"} never been
              used. Revoke anything you are not relying on.
            </p>
          </>
        )}
      </Card>

      {canViewAuditTrail && (
        <Card className="p-6">
          <IpAllowlistPanel workspaceId={workspaceId} initialEntries={ipAllowlist} />
        </Card>
      )}

      <Card className="gap-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <h2 className="font-medium">Audit trail</h2>
          {canViewAuditTrail && (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/dashboard/${workspaceId}/audit-logs`}>View all</Link>
            </Button>
          )}
        </div>
        <Separator />
        {!canViewAuditTrail ? (
          <p className="text-sm text-muted-foreground">
            Only workspace admins and owners can view the audit trail.
          </p>
        ) : recentEvents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing has been recorded for this workspace yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {recentEvents.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-3 text-sm">
                <span className="font-mono text-xs text-muted-foreground">{entry.action}</span>
                <span className="whitespace-nowrap text-xs text-muted-foreground">
                  {formatDateTime(entry.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <span className="w-36 shrink-0 text-sm text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 truncate text-sm">{value}</span>
    </div>
  );
}

export const metadata = {
  title: "Security · AgentVerse",
};
