"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { createKnowledgeBaseAction } from "@/lib/api/actions";

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

/** Mirrors `CreateKnowledgeBaseRequest`'s constraints exactly, so a
 * form-side rejection and a server-side rejection never disagree. */
const schema = z.object({
  name: z.string().min(1, "Name is required").max(120),
  description: z.string().max(1000).optional(),
});

type FormValues = z.infer<typeof schema>;

export function CreateKnowledgeBaseDialog({
  workspaceId,
}: {
  workspaceId: string;
}): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", description: "" },
  });

  async function onSubmit(values: FormValues): Promise<void> {
    try {
      const kb = await createKnowledgeBaseAction(
        workspaceId,
        values.name,
        values.description?.trim() || null
      );
      setOpen(false);
      form.reset();
      router.push(`/dashboard/${workspaceId}/knowledge/${kb.id}`);
    } catch {
      toast.error("Could not create the knowledge base — try again.");
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
        <Button>
          <Plus />
          New knowledge base
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New knowledge base</DialogTitle>
          <DialogDescription>
            Upload documents your agents can cite. You&apos;ll add files next.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Product documentation" autoFocus {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description (optional)</FormLabel>
                  <FormControl>
                    <Textarea placeholder="What does this cover?" rows={3} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "Creating…" : "Create knowledge base"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
