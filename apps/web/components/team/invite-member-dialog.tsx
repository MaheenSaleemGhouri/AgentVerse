"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { UserPlus } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { Role } from "@/lib/api/workspaces";
import { useInviteMember } from "@/lib/queries/workspace";
import { ASSIGNABLE_ROLES, ROLE_DESCRIPTIONS } from "@/lib/roles";

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
  FormDescription,
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

const schema = z.object({
  userId: z.string().min(1, "User ID is required").max(128),
  role: z.enum(["admin", "member", "viewer"]),
});

type FormValues = z.infer<typeof schema>;

/**
 * Adds an existing user to the workspace by ID.
 *
 * Email invitations need a notification service, which is a later phase
 * — so this reflects what the API actually does (`POST /members` takes a
 * `user_id`) rather than presenting an email field that would silently
 * fail.
 */
export function InviteMemberDialog({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const inviteMember = useInviteMember(workspaceId);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { userId: "", role: "member" },
  });

  function onSubmit(values: FormValues): void {
    inviteMember.mutate(
      { userId: values.userId.trim(), role: values.role as Role },
      {
        onSuccess: () => {
          setOpen(false);
          form.reset();
        },
      }
    );
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
          <UserPlus />
          Add member
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a member</DialogTitle>
          <DialogDescription>
            Grant an existing AgentVerse user access to this workspace.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
            <FormField
              control={form.control}
              name="userId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>User ID</FormLabel>
                  <FormControl>
                    <Input placeholder="usr_…" autoFocus className="font-mono" {...field} />
                  </FormControl>
                  <FormDescription>
                    They can find this on their profile page.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Role</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {ASSIGNABLE_ROLES.map((role) => (
                        <SelectItem key={role} value={role}>
                          <span className="capitalize">{role}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    {ROLE_DESCRIPTIONS[field.value as Role]}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="submit" disabled={inviteMember.isPending}>
                {inviteMember.isPending ? "Adding…" : "Add member"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
