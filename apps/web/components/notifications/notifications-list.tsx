"use client";

import { AlertTriangle, Bell, CheckCheck, Info, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  markAllNotificationsReadAction,
  markNotificationReadAction,
} from "@/lib/api/actions";
import type { Notification } from "@/lib/api/notifications";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * The workspace's notification feed.
 *
 * Read state is per workspace, not per user, matching the backend: these
 * are facts about the workspace, and once someone has dealt with a
 * failed payment it should stop nagging everyone. The copy says
 * "everyone" rather than "you" for that reason — a control whose scope
 * is wider than the reader expects is worse than no control.
 *
 * Severity is conveyed by an icon *and* a label, never by colour alone
 * (CLAUDE.md §15).
 */
const SEVERITY: Record<
  string,
  { icon: React.ComponentType<{ className?: string }>; label: string; className: string }
> = {
  info: { icon: Info, label: "Info", className: "text-muted-foreground" },
  warning: { icon: TriangleAlert, label: "Needs attention", className: "text-warning" },
  critical: { icon: AlertTriangle, label: "Action required", className: "text-destructive" },
};

export function NotificationsList({
  workspaceId,
  notifications,
  unreadCount,
}: {
  workspaceId: string;
  notifications: Notification[];
  unreadCount: number;
}): React.JSX.Element {
  const router = useRouter();
  const [isBusy, setIsBusy] = React.useState(false);

  async function markRead(id: string): Promise<void> {
    setIsBusy(true);
    try {
      await markNotificationReadAction(workspaceId, id);
      router.refresh();
    } catch {
      toast.error("Could not mark that notification as read.");
    } finally {
      setIsBusy(false);
    }
  }

  async function markAll(): Promise<void> {
    setIsBusy(true);
    try {
      const result = await markAllNotificationsReadAction(workspaceId);
      toast.success(
        result.marked === 1
          ? "1 notification marked as read."
          : `${result.marked} notifications marked as read.`
      );
      router.refresh();
    } catch {
      toast.error("Could not mark notifications as read.");
    } finally {
      setIsBusy(false);
    }
  }

  if (notifications.length === 0) {
    return (
      <EmptyState
        icon={Bell}
        title="Nothing to catch up on"
        description="Billing events, quota thresholds and referral rewards for this workspace appear here."
      />
    );
  }

  return (
    <div className="space-y-4">
      {unreadCount > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {unreadCount} unread {unreadCount === 1 ? "notification" : "notifications"}
          </p>
          <Button variant="outline" size="sm" onClick={markAll} disabled={isBusy}>
            <CheckCheck className="size-4" aria-hidden="true" />
            {/* Says "for everyone" because read state is workspace-wide;
                a control whose scope is wider than the reader expects is
                worse than no control. */}
            Mark all read for everyone
          </Button>
        </div>
      )}

      <ul className="space-y-3">
        {notifications.map((notification) => {
          const severity = SEVERITY[notification.severity] ?? SEVERITY.info;
          const Icon = severity!.icon;
          return (
            <li key={notification.id}>
              <Card
                className={cn(
                  "flex-row items-start gap-4 p-5",
                  !notification.is_read && "border-primary/40"
                )}
              >
                <Icon
                  className={cn("mt-0.5 size-4 shrink-0", severity!.className)}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">{notification.title}</p>
                    {!notification.is_read && (
                      <Badge variant="secondary" className="text-xs">
                        Unread
                      </Badge>
                    )}
                    {/* The severity label, so urgency is never carried
                        by the icon's colour alone. */}
                    <span className="sr-only">{severity!.label}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">{notification.body}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatRelativeTime(notification.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  {notification.action_path && (
                    <Button variant="outline" size="sm" asChild>
                      <Link href={notification.action_path}>Open</Link>
                    </Button>
                  )}
                  {!notification.is_read && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => markRead(notification.id)}
                      disabled={isBusy}
                    >
                      Mark read
                      <span className="sr-only"> — {notification.title}</span>
                    </Button>
                  )}
                </div>
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
