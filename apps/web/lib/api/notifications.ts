import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * Generated from the API's OpenAPI schema — never hand-written, so a
 * backend field rename fails the build here rather than becoming
 * `undefined` at runtime.
 */
export type Notification = components["schemas"]["NotificationResponse"];
export type NotificationList = components["schemas"]["NotificationListResponse"];

export async function listNotifications(
  workspaceId: string,
  options: { unreadOnly?: boolean; limit?: number } = {}
): Promise<NotificationList> {
  const params = new URLSearchParams();
  if (options.unreadOnly) params.set("unread_only", "true");
  if (options.limit) params.set("limit", String(options.limit));
  const query = params.toString();
  return apiFetch<NotificationList>(
    `/api/v1/workspaces/${workspaceId}/notifications${query ? `?${query}` : ""}`
  );
}

export async function markNotificationRead(
  workspaceId: string,
  notificationId: string
): Promise<void> {
  await apiFetch(
    `/api/v1/workspaces/${workspaceId}/notifications/${notificationId}/read`,
    { method: "POST", skipJson: true }
  );
}

export async function markAllNotificationsRead(
  workspaceId: string
): Promise<{ marked: number }> {
  return apiFetch(`/api/v1/workspaces/${workspaceId}/notifications/read-all`, {
    method: "POST",
  });
}
