"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { createTeamAction } from "@/lib/api/actions";
import type { Topology } from "@/lib/api/teams";
import { TOPOLOGIES } from "@/lib/teams-vocabulary";
import { cn } from "@/lib/utils";

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
import { Textarea } from "@/components/ui/textarea";

/**
 * Topology is chosen at creation because it decides what the builder
 * asks for next — a supervisor/worker team needs a supervisor seat, a
 * planner/executor/critic team needs three specific ones. Asking after
 * the roster is built would mean telling the user their existing seats
 * are now wrong.
 */
const createTeamSchema = z.object({
  name: z.string().min(1, "Name is required").max(200),
  objective: z.string().max(4000).optional(),
  topology: z.enum(["supervisor_worker", "planner_executor_critic", "sequential", "parallel"]),
});

type CreateTeamFormValues = z.infer<typeof createTeamSchema>;

const TOPOLOGY_ORDER: readonly Topology[] = [
  "supervisor_worker",
  "sequential",
  "planner_executor_critic",
  "parallel",
];

export function CreateTeamDialog({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const form = useForm<CreateTeamFormValues>({
    resolver: zodResolver(createTeamSchema),
    // Supervisor/worker is the default because it is the topology that
    // degrades most gracefully: one supervisor and one worker is a
    // working team, where planner/executor/critic needs three seats
    // filled before it can run at all.
    defaultValues: { name: "", objective: "", topology: "supervisor_worker" },
  });

  const selected = form.watch("topology");

  async function onSubmit(values: CreateTeamFormValues): Promise<void> {
    try {
      const team = await createTeamAction(workspaceId, {
        name: values.name,
        topology: values.topology,
        objective: values.objective?.trim() || null,
      });
      setOpen(false);
      form.reset();
      router.push(`/dashboard/${workspaceId}/teams/${team.id}`);
    } catch {
      toast.error("Could not create the team — try again.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          New team
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New AI team</DialogTitle>
          <DialogDescription>
            A team runs several of your existing agents together. Agents keep their own
            instructions, model, and knowledge — the team decides how they collaborate.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Research crew" autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="topology"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>How they work together</FormLabel>
                  {/* A radio group of cards rather than a select: the
                      choice changes what the builder asks for next, so
                      the trade-offs need to be readable at the moment of
                      choosing, not hidden behind a dropdown. */}
                  <div role="radiogroup" aria-label="Topology" className="grid gap-2">
                    {TOPOLOGY_ORDER.map((topology) => {
                      const meta = TOPOLOGIES[topology];
                      const Icon = meta.icon;
                      const isSelected = selected === topology;
                      return (
                        <button
                          key={topology}
                          type="button"
                          role="radio"
                          aria-checked={isSelected}
                          onClick={() => field.onChange(topology)}
                          className={cn(
                            "flex items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                            "focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
                            isSelected
                              ? "border-primary bg-accent"
                              : "border-border hover:border-primary/40"
                          )}
                        >
                          <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                          <span className="min-w-0">
                            <span className="block text-sm font-medium">{meta.label}</span>
                            <span className="block text-xs text-muted-foreground">
                              {meta.summary}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="objective"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Objective (optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder="Research a competitor and produce a one-page brief."
                      {...field}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    Added to every member&apos;s instructions. Their own instructions still
                    apply.
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
                disabled={form.formState.isSubmitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "Creating…" : "Create team"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
