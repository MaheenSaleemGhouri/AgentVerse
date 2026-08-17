"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { saveAgentVersionAction } from "@/lib/api/actions";
import type { AgentVersion } from "@/lib/api/agents";
import { useAgentBuilderStore, type BuilderPanelTab } from "@/lib/stores/agent-builder-store";
import { agentConfigSchema, BUILTIN_TOOLS, MODEL_CATALOG, type AgentConfigFormValues } from "@/lib/validation/agent-config";

import { KnowledgeBaseAttach } from "@/components/agents/knowledge-base-attach";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

export function AgentConfigPanel({
  workspaceId,
  agentId,
  version,
  onSaved,
}: {
  workspaceId: string;
  agentId: string;
  version: AgentVersion;
  onSaved: (version: AgentVersion) => void;
}): React.JSX.Element {
  const activeTab = useAgentBuilderStore((s) => s.activeTab);
  const setActiveTab = useAgentBuilderStore((s) => s.setActiveTab);
  const setDirty = useAgentBuilderStore((s) => s.setDirty);

  const form = useForm<AgentConfigFormValues>({
    resolver: zodResolver(agentConfigSchema),
    defaultValues: {
      model: version.model,
      system_instructions: version.system_instructions,
      temperature: version.temperature,
      max_output_tokens: version.max_output_tokens,
      tools: version.tools,
      knowledge_base_ids: version.knowledge_base_ids,
    },
  });

  useEffect(() => {
    const subscription = form.watch(() => setDirty(form.formState.isDirty));
    return () => subscription.unsubscribe();
  }, [form, setDirty]);

  async function onSubmit(values: AgentConfigFormValues): Promise<void> {
    try {
      const saved = await saveAgentVersionAction(workspaceId, agentId, values);
      form.reset(values);
      setDirty(false);
      onSaved(saved);
      toast.success(`Saved as version ${saved.version_number}`);
    } catch {
      toast.error("Could not save changes — try again.");
    }
  }

  return (
    // The inspector panel from §14's layout — its own bordered surface,
    // matching the canvas rather than sitting bare beside it.
    <Card className="flex h-full flex-col gap-0 p-5">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex h-full flex-col gap-4">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as BuilderPanelTab)}>
            <TabsList className="w-full">
              <TabsTrigger value="instructions">Instructions</TabsTrigger>
              <TabsTrigger value="model">Model</TabsTrigger>
              <TabsTrigger value="tools">Tools</TabsTrigger>
              <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
            </TabsList>

            <TabsContent value="instructions" className="mt-4">
              <FormField
                control={form.control}
                name="system_instructions"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>System instructions</FormLabel>
                    <FormControl>
                      <Textarea
                        rows={12}
                        placeholder="You are a helpful assistant that..."
                        className="font-mono text-sm"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Defines the agent&apos;s behavior. Reaches the model on every run.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </TabsContent>

            <TabsContent value="model" className="mt-4 flex flex-col gap-4">
              <FormField
                control={form.control}
                name="model"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Model</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {MODEL_CATALOG.map((group) => (
                          <SelectGroup key={group.provider}>
                            <SelectLabel>{group.provider}</SelectLabel>
                            {group.models.map((model) => (
                              <SelectItem key={model} value={model}>
                                {model}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="temperature"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Temperature</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step={0.1}
                        min={0}
                        max={2}
                        value={field.value ?? ""}
                        onChange={(e) =>
                          field.onChange(e.target.value === "" ? null : Number(e.target.value))
                        }
                      />
                    </FormControl>
                    <FormDescription>
                      0 = deterministic, 2 = most random. Optional.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="max_output_tokens"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max output tokens</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={32000}
                        value={field.value ?? ""}
                        onChange={(e) =>
                          field.onChange(e.target.value === "" ? null : Number(e.target.value))
                        }
                      />
                    </FormControl>
                    <FormDescription>Caps run cost and latency. Optional.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </TabsContent>

            <TabsContent value="tools" className="mt-4">
              <FormField
                control={form.control}
                name="tools"
                render={({ field }) => (
                  <FormItem className="flex flex-col gap-3">
                    {/* MCP tools are not selected per agent-version: every
                        run attaches whatever the workspace has installed
                        and enabled at `/mcp`, resolved automatically by
                        the worker (agent_run_job.py's `_attach_mcp`). A
                        per-agent checklist here would just be a second,
                        out-of-sync copy of that workspace list. */}
                    <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                      MCP tools from your installed integrations are attached to every run
                      automatically.{" "}
                      <Link
                        href={`/dashboard/${workspaceId}/mcp`}
                        className="font-medium underline"
                      >
                        Manage integrations
                      </Link>
                    </p>
                    {BUILTIN_TOOLS.map((tool) => {
                      const checked = field.value.includes(tool.id);
                      return (
                        <div
                          key={tool.id}
                          className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                        >
                          <div>
                            <FormLabel className="font-medium">{tool.label}</FormLabel>
                            <p className="text-sm text-muted-foreground">{tool.description}</p>
                          </div>
                          <FormControl>
                            <Switch
                              checked={checked}
                              onCheckedChange={(next) => {
                                field.onChange(
                                  next
                                    ? [...field.value, tool.id]
                                    : field.value.filter((id) => id !== tool.id)
                                );
                              }}
                              aria-label={`Enable ${tool.label}`}
                            />
                          </FormControl>
                        </div>
                      );
                    })}
                    <FormMessage />
                  </FormItem>
                )}
              />
            </TabsContent>
            <TabsContent value="knowledge" className="mt-4">
              <FormField
                control={form.control}
                name="knowledge_base_ids"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Grounding</FormLabel>
                    <FormDescription>
                      Attached documents are retrieved on every run and cited in the answer.
                    </FormDescription>
                    <FormControl>
                      <div>
                        <KnowledgeBaseAttach
                          workspaceId={workspaceId}
                          value={field.value}
                          onChange={field.onChange}
                        />
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </TabsContent>
          </Tabs>

          <Button type="submit" disabled={form.formState.isSubmitting || !form.formState.isDirty}>
            {form.formState.isSubmitting ? "Saving…" : "Save changes"}
          </Button>
        </form>
      </Form>
    </Card>
  );
}
