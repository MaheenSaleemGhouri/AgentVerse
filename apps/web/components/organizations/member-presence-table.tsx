import * as React from "react";

import type { MemberPresence } from "@/lib/api/organizations";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

import { StatusBadge } from "@/components/patterns/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/**
 * Reduces a user-agent string to something a human can scan.
 *
 * Deliberately crude: full UA parsing needs a maintained database and
 * gets it wrong anyway, and the question this column answers is "does
 * that look like my machine?", not "which exact build?".
 */
function describeDevice(userAgent: string | null): string {
  if (!userAgent) return "Unknown device";
  const os = /Windows/i.test(userAgent)
    ? "Windows"
    : /Mac OS X|Macintosh/i.test(userAgent)
      ? "macOS"
      : /Android/i.test(userAgent)
        ? "Android"
        : /iPhone|iPad|iOS/i.test(userAgent)
          ? "iOS"
          : /Linux/i.test(userAgent)
            ? "Linux"
            : "Unknown OS";
  const browser = /Edg\//i.test(userAgent)
    ? "Edge"
    : /Chrome\//i.test(userAgent)
      ? "Chrome"
      : /Safari\//i.test(userAgent)
        ? "Safari"
        : /Firefox\//i.test(userAgent)
          ? "Firefox"
          : "Unknown browser";
  return `${browser} on ${os}`;
}

export function MemberPresenceTable({
  members,
}: {
  members: MemberPresence[];
}): React.JSX.Element {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Member</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Last sign-in</TableHead>
          <TableHead>Last device</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => (
          <TableRow key={member.user_id}>
            <TableCell>
              <div className="font-medium">{member.name}</div>
              <div className="text-xs text-muted-foreground">{member.email}</div>
            </TableCell>
            <TableCell>
              <StatusBadge tone={member.role === "owner" ? "brand" : "neutral"}>
                {member.role}
              </StatusBadge>
            </TableCell>
            <TableCell>
              {member.suspended_at ? (
                <StatusBadge tone="danger">suspended</StatusBadge>
              ) : member.has_active_session ? (
                // "Signed in", not "online": the platform knows a session
                // is unexpired, not that anyone is looking at the screen.
                <StatusBadge tone="success">signed in</StatusBadge>
              ) : (
                <StatusBadge tone="neutral">signed out</StatusBadge>
              )}
            </TableCell>
            <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
              {member.last_login_at ? (
                <span title={formatDateTime(member.last_login_at)}>
                  {formatRelativeTime(member.last_login_at)}
                </span>
              ) : (
                "Never"
              )}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {describeDevice(member.last_user_agent)}
              {member.last_ip_address ? (
                <div className="text-xs">{member.last_ip_address}</div>
              ) : null}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
