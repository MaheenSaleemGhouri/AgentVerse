"use client";

import { BookOpen, Cpu, Hash, Thermometer, Wrench } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Agent, AgentVersion } from "@/lib/api/agents";
import type { KnowledgeBase } from "@/lib/api/knowledge";
import { formatDateTime } from "@/lib/format";
import { BUILTIN_TOOLS } from "@/lib/validation/agent-config";

import { CopyButton } from "@/components/patterns/copy-button";
import { IntegrationPending } from "@/components/patterns/integration-pending";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function AgentOverview({
  workspaceId,
  agent,
  version,
  knowledgeBases,
}: {
  workspaceId: string;
  agent: Agent;
  version: AgentVersion | null;
  knowledgeBases: KnowledgeBase[];
}): React.JSX.Element {
  const attached = React.useMemo(() => {
    const ids = new Set(version?.knowledge_base_ids ?? []);
    return knowledgeBases.filter((kb) => ids.has(kb.id));
  }, [knowledgeBases, version]);

  // A KB attached to the version but no longer in the workspace list was
  // deleted after publish. Grounding silently skips it at run time, so
  // surfacing it here is the only place the user can find out.
  const missingCount = (version?.knowledge_base_ids.length ?? 0) - attached.length;

  return (
    <Tabs defaultValue="configuration">
      <TabsList>
        <TabsTrigger value="configuration">Configuration</TabsTrigger>
        <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
        <TabsTrigger value="runs">Runs</TabsTrigger>
      </TabsList>

      <TabsContent value="configuration" className="mt-4 space-y-4">
        {!version ? (
          <Alert tone="warning">
            <Cpu />
            <AlertTitle>No version yet</AlertTitle>
            <AlertDescription>
              This agent has no saved configuration. Open the builder to create its first version.
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <FactCard icon={Hash} label="Version" value={`v${version.version_number}`} />
              <FactCard icon={Cpu} label="Model" value={version.model} mono />
              <FactCard
                icon={Thermometer}
                label="Temperature"
                value={version.temperature === null ? "Provider default" : String(version.temperature)}
              />
              <FactCard
                icon={Wrench}
                label="Max output tokens"
                value={
                  version.max_output_tokens === null
                    ? "Provider default"
                    : String(version.max_output_tokens)
                }
              />
            </div>

            <Card className="gap-3 p-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">System instructions</h3>
                <CopyButton value={version.system_instructions} label="Copy instructions" />
              </div>
              <ScrollArea className="max-h-72">
                <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
                  {version.system_instructions}
                </pre>
              </ScrollArea>
            </Card>

            <Card className="gap-3 p-5">
              <h3 className="text-sm font-medium">Tools</h3>
              {version.tools.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No tools enabled — this agent answers from its instructions and knowledge alone.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {version.tools.map((toolId) => {
                    const tool = BUILTIN_TOOLS.find((candidate) => candidate.id === toolId);
                    return (
                      <Badge key={toolId} variant="outline" className="gap-1.5">
                        <Wrench className="size-3" aria-hidden="true" />
                        {tool?.label ?? toolId}
                      </Badge>
                    );
                  })}
                </div>
              )}
            </Card>

            <Card className="gap-2 p-5">
              <h3 className="text-sm font-medium">Identifiers</h3>
              <Separator />
              <IdRow label="Agent ID" value={agent.id} />
              <IdRow label="Version ID" value={version.id} />
              <p className="text-xs text-muted-foreground">
                Created {formatDateTime(version.created_at)}
              </p>
            </Card>
          </>
        )}
      </TabsContent>

      <TabsContent value="knowledge" className="mt-4 space-y-4">
        {missingCount > 0 && (
          <Alert tone="warning">
            <BookOpen />
            <AlertTitle>
              {missingCount} attached knowledge base{missingCount > 1 ? "s are" : " is"} unavailable
            </AlertTitle>
            <AlertDescription>
              They were deleted after this version was saved. Runs will skip them and answer with
              whatever remains — save a new version to remove them from the configuration.
            </AlertDescription>
          </Alert>
        )}

        {attached.length === 0 ? (
          <Card className="gap-2 p-5">
            <h3 className="text-sm font-medium">Not grounded</h3>
            <p className="text-sm text-muted-foreground">
              This agent has no knowledge bases attached, so it answers from its instructions alone
              and cannot cite sources.{" "}
              <Link
                href={`/dashboard/${workspaceId}/agents/${agent.id}/builder`}
                className="text-primary underline underline-offset-4"
              >
                Attach one in the builder
              </Link>
              .
            </p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {attached.map((kb) => (
              <Card key={kb.id} className="gap-1 p-5">
                <Link
                  href={`/dashboard/${workspaceId}/knowledge/${kb.id}`}
                  className="font-medium hover:underline"
                >
                  {kb.name}
                </Link>
                <p className="text-sm text-muted-foreground">
                  {kb.description ?? "No description"}
                </p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  {kb.embedding_model} v{kb.embedding_model_version}
                </p>
              </Card>
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="runs" className="mt-4">
        <IntegrationPending feature="runHistory" />
      </TabsContent>
    </Tabs>
  );
}

function FactCard({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  mono?: boolean;
}): React.JSX.Element {
  return (
    <Card className="gap-1 p-4">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </span>
      <span className={mono ? "font-mono text-sm font-medium" : "text-sm font-medium"}>
        {value}
      </span>
    </Card>
  );
}

function IdRow({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-xs text-muted-foreground">{label}</span>
      <code className="min-w-0 flex-1 truncate font-mono text-xs">{value}</code>
      <CopyButton value={value} label={`Copy ${label}`} size="icon-xs" />
    </div>
  );
}
