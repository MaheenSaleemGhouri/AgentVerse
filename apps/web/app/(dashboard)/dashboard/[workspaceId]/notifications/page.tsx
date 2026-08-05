import * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { PageHeader } from "@/components/patterns/page-header";
import { NotificationsList } from "@/components/notifications/notifications-list";
import { listNotificationsAction } from "@/lib/api/actions";

/**
 * Notifications.
 *
 * Real data — the backend this page was waiting on shipped with the
 * billing lifecycle work, so the `IntegrationPending` panel and its
 * registry entry are both gone.
 *
 * Server-fetched and passed down (CLAUDE.md §6), so the feed is
 * populated on first paint rather than flashing a skeleton.
 */
export default async function NotificationsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  const header = (
    <PageHeader
      title="Notifications"
      description="Billing events, quota thresholds, and referral rewards for this workspace."
    />
  );

  let feed;
  try {
    feed = await listNotificationsAction(workspaceId);
  } catch {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <ErrorState
          title="Could not load notifications"
          description="We could not reach the notification service. Nothing has been lost — this page recovers on its own once the service responds."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {header}
      <NotificationsList
        workspaceId={workspaceId}
        notifications={feed.data}
        unreadCount={feed.unread_count}
      />
    </div>
  );
}

export const metadata = {
  title: "Notifications · AgentVerse",
};
