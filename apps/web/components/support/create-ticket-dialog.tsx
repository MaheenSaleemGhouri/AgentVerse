"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import type { Agent } from "@/lib/api/agents";
import { useCreateSupportTicket } from "@/lib/queries/support-tickets";
import {
  createSupportTicketSchema,
  type CreateSupportTicketFormValues,
} from "@/lib/validation/support-ticket";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

/**
 * Files a support ticket that immediately runs the chosen agent to
 * triage it (Phase 11's dogfooded automation) — no separate "submit"
 * step, filing *is* triggering the run.
 */
export function CreateTicketDialog({
  workspaceId,
  agents,
}: {
  workspaceId: string;
  agents: Agent[];
}): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const createTicket = useCreateSupportTicket(workspaceId);
  const form = useForm<CreateSupportTicketFormValues>({
    resolver: zodResolver(createSupportTicketSchema),
    defaultValues: { agent_id: agents[0]?.id ?? "", subject: "", body: "" },
  });

  async function onSubmit(values: CreateSupportTicketFormValues): Promise<void> {
    try {
      const ticket = await createTicket.mutateAsync(values);
      setOpen(false);
      form.reset();
      router.push(`/dashboard/${workspaceId}/support/${ticket.id}`);
    } catch {
      toast.error("Could not file this ticket — try again.");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) form.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button disabled={agents.length === 0}>
          <Plus />
          New ticket
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New support ticket</DialogTitle>
          <DialogDescription>
            The agent you choose triages this immediately — category, priority, and a draft
            reply, ready to review.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
            <FormField
              control={form.control}
              name="agent_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Triage agent</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Choose an agent" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {agents.map((agent) => (
                        <SelectItem key={agent.id} value={agent.id}>
                          {agent.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="subject"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Subject</FormLabel>
                  <FormControl>
                    <Input placeholder="Can't log in" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="body"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Details</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={5}
                      placeholder="What's going on?"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="submit" disabled={createTicket.isPending}>
                {createTicket.isPending ? "Filing…" : "File ticket"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
