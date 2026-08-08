"use client";

import { Bot, LayoutGrid, List, Search } from "lucide-react";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import { formatRelativeTime } from "@/lib/format";
import { useAgents } from "@/lib/queries/agents";
import { cn } from "@/lib/utils";

import { AgentCard } from "@/components/agents/agent-card";
import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import { CreateAgentDialog } from "@/components/agents/create-agent-dialog";
import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Link from "next/link";

type StatusFilter = "all" | "draft" | "active" | "archived";

const FILTERS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "active", label: "Published" },
  { value: "archived", label: "Archived" },
];

type SortKey = "recent" | "name" | "status";

/**
 * Sort options are limited to fields `AgentResponse` actually carries.
 * "Last run" and "most run" are the obvious other choices and are
 * deliberately absent — runs have no read path, so either would be a
 * control that silently sorts by nothing.
 */
const SORTERS: Record<SortKey, (a: Agent, b: Agent) => number> = {
  recent: (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
  name: (a, b) => a.name.localeCompare(b.name),
  // Published first, then drafts, then archived — the order someone
  // scanning for "what is live" wants, not alphabetical on the status
  // string, which would put archived at the top.
  status: (a, b) =>
    STATUS_RANK.indexOf(a.status) - STATUS_RANK.indexOf(b.status) ||
    a.name.localeCompare(b.name),
};

const STATUS_RANK = ["active", "draft", "archived"];

const SORT_OPTIONS: ReadonlyArray<{ value: SortKey; label: string }> = [
  { value: "recent", label: "Recently updated" },
  { value: "name", label: "Name (A–Z)" },
  { value: "status", label: "Status" },
];

/**
 * Filtering and view mode are local UI state, never a query param round
 * trip — the full list is already in the cache, so re-filtering it
 * client-side is instant where a refetch would not be.
 */
export function AgentsGrid({
  workspaceId,
  initialAgents,
}: {
  workspaceId: string;
  initialAgents: Agent[];
}): React.JSX.Element {
  const { data: agents, isLoading, isError, refetch } = useAgents(workspaceId, initialAgents);
  const [query, setQuery] = React.useState("");
  const [status, setStatus] = React.useState<StatusFilter>("all");
  const [view, setView] = React.useState<"grid" | "table">("grid");
  const [sort, setSort] = React.useState<SortKey>("recent");

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matched = (agents ?? []).filter((agent) => {
      if (status !== "all" && agent.status !== status) return false;
      if (!needle) return true;
      return (
        agent.name.toLowerCase().includes(needle) ||
        (agent.description ?? "").toLowerCase().includes(needle)
      );
    });

    // Sorted on a copy — `agents` is TanStack Query's cached array, and
    // sorting it in place would mutate the cache under every other
    // consumer.
    return [...matched].sort(SORTERS[sort]);
  }, [agents, query, status, sort]);

  if (isError) {
    return (
      <ErrorState
        title="Could not load agents"
        description="The agents API did not respond. Your session may have expired."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading && !agents) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-36 rounded-xl" />
        ))}
      </div>
    );
  }

  if ((agents ?? []).length === 0) {
    return (
      <EmptyState
        icon={Bot}
        mascot="waving"
        title="No agents yet"
        description="An agent is a stored configuration — instructions, model, tools, and knowledge. Create one to reach a working run in minutes."
        action={<CreateAgentDialog workspaceId={workspaceId} />}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search agents…"
            aria-label="Search agents"
            className="pl-9"
          />
        </div>

        <Tabs value={status} onValueChange={(value) => setStatus(value as StatusFilter)}>
          <TabsList>
            {FILTERS.map((filter) => (
              <TabsTrigger key={filter.value} value={filter.value}>
                {filter.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Select value={sort} onValueChange={(value) => setSort(value as SortKey)}>
          <SelectTrigger size="sm" className="w-44" aria-label="Sort agents">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
          <Button
            variant={view === "grid" ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Grid view"
            aria-pressed={view === "grid"}
            onClick={() => setView("grid")}
          >
            <LayoutGrid />
          </Button>
          <Button
            variant={view === "table" ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Table view"
            aria-pressed={view === "table"}
            onClick={() => setView("table")}
          >
            <List />
          </Button>
        </div>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No agents match"
          description="Try a different search term, or clear the status filter."
          action={
            <Button
              variant="outline"
              onClick={() => {
                setQuery("");
                setStatus("all");
              }}
            >
              Clear filters
            </Button>
          }
        />
      ) : view === "grid" ? (
        <div className={cn("grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3")}>
          {visible.map((agent) => (
            <AgentCard key={agent.id} workspaceId={workspaceId} agent={agent} />
          ))}
        </div>
      ) : (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((agent) => (
                <TableRow key={agent.id}>
                  <TableCell>
                    <Link
                      href={`/dashboard/${workspaceId}/agents/${agent.id}`}
                      className="font-medium hover:underline"
                    >
                      {agent.name}
                    </Link>
                    <p className="truncate text-xs text-muted-foreground">
                      {agent.description ?? "No description"}
                    </p>
                  </TableCell>
                  <TableCell>
                    <AgentStatusBadge status={agent.status} />
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                    {formatRelativeTime(agent.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
