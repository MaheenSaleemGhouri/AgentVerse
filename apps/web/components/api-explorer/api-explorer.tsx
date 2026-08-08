"use client";

import { Play, Terminal } from "lucide-react";
import * as React from "react";

import { sendExplorerRequest, type ExplorerResult } from "@/lib/api-explorer/actions";
import {
  EXPLORER_ENDPOINTS,
  type ExplorerEndpoint,
  buildPath,
  isComplete,
} from "@/lib/api-explorer/endpoints";
import { curlSnippet, pythonSnippet, typescriptSnippet } from "@/lib/api-explorer/snippets";
import { cn } from "@/lib/utils";

import { CopyButton } from "@/components/patterns/copy-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const GROUPS = [...new Set(EXPLORER_ENDPOINTS.map((endpoint) => endpoint.group))];

/**
 * Try a request, see the real response, copy the code.
 *
 * Requests execute through a Server Action using the caller's session,
 * so nothing here needs — or is given — an API key. That is deliberate:
 * keys are stored hashed and cannot be read back, so an explorer that
 * asked for one would be asking people to paste a credential into a form
 * to see data they are already authenticated for.
 *
 * The snippets it prints *do* use a key, because that is what a caller
 * outside the browser needs. They read it from the environment rather
 * than embedding one.
 */
export function ApiExplorer({
  workspaceId,
  publicBaseUrl,
}: {
  workspaceId: string;
  publicBaseUrl: string;
}): React.JSX.Element {
  const [selectedId, setSelectedId] = React.useState(EXPLORER_ENDPOINTS[0]?.id ?? "");
  const [pathValues, setPathValues] = React.useState<Record<string, string>>({});
  const [queryValues, setQueryValues] = React.useState<Record<string, string>>({});
  const [result, setResult] = React.useState<ExplorerResult | null>(null);
  const [sending, setSending] = React.useState(false);

  const endpoint =
    EXPLORER_ENDPOINTS.find((candidate) => candidate.id === selectedId) ?? EXPLORER_ENDPOINTS[0];

  function select(next: ExplorerEndpoint): void {
    setSelectedId(next.id);
    // Parameters do not carry across endpoints — an agent id left in the
    // form from the previous endpoint would silently produce a 404 that
    // looks like the endpoint is broken.
    setPathValues({});
    setQueryValues({});
    setResult(null);
  }

  if (!endpoint) return <></>;

  const path = buildPath(endpoint, workspaceId, pathValues, queryValues);
  const ready = isComplete(endpoint, pathValues, queryValues);

  async function onSend(): Promise<void> {
    if (!endpoint) return;
    setSending(true);
    try {
      setResult(await sendExplorerRequest(workspaceId, endpoint.id, pathValues, queryValues));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <nav aria-label="Endpoints" className="w-full shrink-0 lg:w-64">
        <div className="flex flex-col gap-5">
          {GROUPS.map((group) => (
            <div key={group}>
              <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {group}
              </h2>
              <ul className="space-y-0.5">
                {EXPLORER_ENDPOINTS.filter((candidate) => candidate.group === group).map(
                  (candidate) => (
                    <li key={candidate.id}>
                      <button
                        type="button"
                        aria-current={candidate.id === endpoint.id ? "true" : undefined}
                        onClick={() => select(candidate)}
                        className={cn(
                          "w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                          candidate.id === endpoint.id
                            ? "bg-accent font-medium text-accent-foreground"
                            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                        )}
                      >
                        {candidate.path.split("/").pop()?.replace(/[{}]/g, "") ?? candidate.id}
                      </button>
                    </li>
                  ),
                )}
              </ul>
            </div>
          ))}
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <Card className="gap-4 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="font-mono">
              {endpoint.method}
            </Badge>
            <code className="min-w-0 flex-1 truncate font-mono text-sm">{path}</code>
            <CopyButton value={`${publicBaseUrl}${path}`} label="Copy URL" />
          </div>
          <p className="text-sm text-muted-foreground">{endpoint.summary}</p>

          {(endpoint.pathParams ?? []).length + (endpoint.queryParams ?? []).length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {(endpoint.pathParams ?? []).map((param) => (
                <div key={param.name} className="space-y-1.5">
                  <Label htmlFor={`path-${param.name}`}>
                    {param.label}
                    {param.required === true && (
                      <span className="text-destructive" aria-hidden="true">
                        {" "}
                        *
                      </span>
                    )}
                  </Label>
                  <Input
                    id={`path-${param.name}`}
                    value={pathValues[param.name] ?? ""}
                    placeholder={param.placeholder ?? ""}
                    required={param.required === true}
                    onChange={(event) =>
                      setPathValues((current) => ({
                        ...current,
                        [param.name]: event.target.value,
                      }))
                    }
                  />
                </div>
              ))}
              {(endpoint.queryParams ?? []).map((param) => (
                <div key={param.name} className="space-y-1.5">
                  <Label htmlFor={`query-${param.name}`}>
                    {param.label}
                    {param.required === true && (
                      <span className="text-destructive" aria-hidden="true">
                        {" "}
                        *
                      </span>
                    )}
                  </Label>
                  <Input
                    id={`query-${param.name}`}
                    value={queryValues[param.name] ?? ""}
                    placeholder={param.placeholder ?? ""}
                    required={param.required === true}
                    onChange={(event) =>
                      setQueryValues((current) => ({
                        ...current,
                        [param.name]: event.target.value,
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button disabled={!ready || sending} onClick={() => void onSend()}>
              <Play />
              {sending ? "Sending…" : "Send request"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Runs as you, in this workspace. Read-only — the explorer offers no endpoint that
              changes anything or costs money.
            </p>
          </div>
        </Card>

        {result && (
          <Card className="gap-3 p-5">
            <div className="flex items-center gap-3">
              <Badge variant={result.ok ? "secondary" : "destructive"}>
                {result.status} {result.ok ? "OK" : "Error"}
              </Badge>
              <span className="text-xs text-muted-foreground">{result.durationMs} ms</span>
              <CopyButton value={result.body} label="Copy response" className="ml-auto" />
            </div>
            <pre
              // `tabIndex` so a keyboard user can scroll a long response
              // without a mouse — a scrollable region that cannot receive
              // focus is unreachable to them.
              tabIndex={0}
              className="max-h-96 overflow-auto rounded-lg border border-border bg-muted/40 p-4 font-mono text-xs leading-5"
            >
              {result.body}
            </pre>
          </Card>
        )}

        <Card className="gap-3 p-5">
          <div className="flex items-center gap-2">
            <Terminal className="size-4 text-muted-foreground" aria-hidden="true" />
            <h2 className="text-sm font-medium">Call it from your own code</h2>
          </div>
          <Tabs defaultValue="curl">
            <TabsList>
              <TabsTrigger value="curl">curl</TabsTrigger>
              <TabsTrigger value="python">Python</TabsTrigger>
              <TabsTrigger value="typescript">TypeScript</TabsTrigger>
            </TabsList>
            {(
              [
                ["curl", curlSnippet(publicBaseUrl, path)],
                ["python", pythonSnippet(publicBaseUrl, path)],
                ["typescript", typescriptSnippet(publicBaseUrl, path)],
              ] as const
            ).map(([value, snippet]) => (
              <TabsContent key={value} value={value} className="pt-3">
                <div className="relative">
                  <CopyButton value={snippet} label="Copy" className="absolute top-2 right-2" />
                  <pre
                    tabIndex={0}
                    className="overflow-x-auto rounded-lg border border-border bg-muted/40 p-4 pr-24 font-mono text-xs leading-5"
                  >
                    {snippet}
                  </pre>
                </div>
              </TabsContent>
            ))}
          </Tabs>
        </Card>
      </div>
    </div>
  );
}
