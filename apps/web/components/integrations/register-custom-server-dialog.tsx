"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useRegisterCustomServer } from "@/lib/queries/integrations";

import { Alert, AlertDescription } from "@/components/ui/alert";
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

/**
 * Registering a user's own MCP endpoint.
 *
 * There is no local-process option, deliberately: a user-supplied
 * command would run on the worker fleet. The form offers only the two
 * HTTP transports, matching what the API accepts — the type excludes
 * stdio rather than validating it away, so the two cannot drift.
 */
const schema = z.object({
  display_name: z.string().min(1, "Name is required").max(200),
  transport: z.enum(["streamable_http", "sse"]),
  endpoint_url: z
    .string()
    .min(1, "Endpoint is required")
    .max(2000)
    .refine((value) => value.startsWith("https://") || value.startsWith("http://"), {
      message: "Must be an http:// or https:// URL",
    }),
  auth_scheme: z.enum(["none", "bearer_token", "api_key", "custom_header"]),
});

type FormValues = z.infer<typeof schema>;

export function RegisterCustomServerDialog({
  workspaceId,
}: {
  workspaceId: string;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const register = useRegisterCustomServer(workspaceId);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      display_name: "",
      transport: "streamable_http",
      endpoint_url: "",
      auth_scheme: "none",
    },
  });

  async function onSubmit(values: FormValues): Promise<void> {
    await register.mutateAsync(values);
    setOpen(false);
    form.reset();
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Plus />
          Add your own
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Register an MCP server</DialogTitle>
          <DialogDescription>
            Connect a Model Context Protocol server you host yourself. Its tools become available
            to any agent you grant access to.
          </DialogDescription>
        </DialogHeader>

        <Alert tone="info">
          <AlertDescription>
            The endpoint must be reachable from the public internet. Addresses on private,
            loopback, or cloud-metadata ranges are refused — an agent must not be usable as a way
            into your internal network.
          </AlertDescription>
        </Alert>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="display_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Internal tools" autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="endpoint_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Endpoint URL</FormLabel>
                  <FormControl>
                    <Input placeholder="https://mcp.example.com/mcp" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="transport"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Transport</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="streamable_http">Streamable HTTP</SelectItem>
                        <SelectItem value="sse">Server-sent events</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="auth_scheme"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Authentication</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="none">None</SelectItem>
                        <SelectItem value="bearer_token">Bearer token</SelectItem>
                        <SelectItem value="api_key">API key</SelectItem>
                        <SelectItem value="custom_header">Custom header</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <p className="text-xs text-muted-foreground">
              You will add the credential itself after registering. It is encrypted before it is
              stored and cannot be read back.
            </p>

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
                {form.formState.isSubmitting ? "Registering…" : "Register server"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
