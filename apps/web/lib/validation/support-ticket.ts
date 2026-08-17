import { z } from "zod";

/**
 * Mirrors apps/api's `CreateSupportTicketRequest` field constraints
 * exactly (support_service/interface/schemas/support_tickets.py).
 */
export const createSupportTicketSchema = z.object({
  agent_id: z.string().min(1, "Choose which agent triages this ticket"),
  subject: z.string().min(1, "Subject is required").max(200),
  body: z.string().min(1, "Describe the issue").max(8000),
});

export type CreateSupportTicketFormValues = z.infer<typeof createSupportTicketSchema>;
