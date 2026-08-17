"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createSupportTicketAction,
  resolveSupportTicketAction,
} from "@/lib/api/actions";
import { queryKeys } from "@/lib/queries/keys";

export function useCreateSupportTicket(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { agent_id: string; subject: string; body: string }) =>
      createSupportTicketAction(workspaceId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.supportTickets.all(workspaceId) });
    },
  });
}

export function useResolveSupportTicket(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticketId: string) => resolveSupportTicketAction(workspaceId, ticketId),
    onSuccess: (_, ticketId) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.supportTickets.detail(workspaceId, ticketId),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.supportTickets.all(workspaceId) });
    },
  });
}
