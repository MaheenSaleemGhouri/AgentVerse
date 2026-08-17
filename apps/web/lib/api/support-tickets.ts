import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type SupportTicket = components["schemas"]["SupportTicketResponse"];
export type SupportTicketPage = components["schemas"]["SupportTicketPage"];

export async function listSupportTickets(workspaceId: string): Promise<SupportTicket[]> {
  const page = await apiFetch<SupportTicketPage>(
    `/api/v1/workspaces/${workspaceId}/support-tickets`,
  );
  return page.data;
}

export async function getSupportTicket(
  workspaceId: string,
  ticketId: string,
): Promise<SupportTicket> {
  return apiFetch<SupportTicket>(
    `/api/v1/workspaces/${workspaceId}/support-tickets/${ticketId}`,
  );
}

export async function createSupportTicket(
  workspaceId: string,
  body: { agent_id: string; subject: string; body: string },
): Promise<SupportTicket> {
  return apiFetch<SupportTicket>(`/api/v1/workspaces/${workspaceId}/support-tickets`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function resolveSupportTicket(
  workspaceId: string,
  ticketId: string,
): Promise<SupportTicket> {
  return apiFetch<SupportTicket>(
    `/api/v1/workspaces/${workspaceId}/support-tickets/${ticketId}/resolve`,
    { method: "POST" },
  );
}
