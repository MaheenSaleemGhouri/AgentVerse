"use client";

import { Check, Download, ExternalLink, Search, Server } from "lucide-react";
import * as React from "react";

import type { InstalledServer, McpServer } from "@/lib/api/integrations";
import {
  AVAILABILITY,
  CATEGORIES,
  CATEGORY_ICONS,
  TRANSPORTS,
} from "@/lib/integrations-vocabulary";
import { useCatalog, useInstallFromCatalog, useInstalledServers } from "@/lib/queries/integrations";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { FilterGroup } from "@/components/patterns/filter-group";
import { StatusBadge } from "@/components/patterns/status-badge";
import { RegisterCustomServerDialog } from "@/components/integrations/register-custom-server-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type CategoryFilter = "all" | (typeof CATEGORIES)[number];

const CATEGORY_FILTERS: ReadonlyArray<{ value: CategoryFilter; label: string }> = [
  { value: "all", label: "All" },
  ...CATEGORIES.map((name) => ({ value: name, label: name })),
];

/**
 * The MCP marketplace.
 *
 * Filtering is client-side over the already-cached catalog: it is dozens
 * of rows, and a round trip per keystroke would be slower than the
 * filter it replaces.
 */
export function Marketplace({
  workspaceId,
  initialCatalog,
  initialInstalled,
}: {
  workspaceId: string;
  initialCatalog: McpServer[];
  initialInstalled: InstalledServer[];
}): React.JSX.Element {
  const catalog = useCatalog(workspaceId, {}, initialCatalog);
  const installed = useInstalledServers(workspaceId, initialInstalled);
  const [query, setQuery] = React.useState("");
  const [category, setCategory] = React.useState<CategoryFilter>("all");

  const installedServerIds = React.useMemo(
    () =>
      new Set(
        (installed.data ?? []).map((server) => server.mcp_server_id).filter(Boolean) as string[]
      ),
    [installed.data]
  );

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (catalog.data ?? []).filter((entry) => {
      if (category !== "all" && entry.category !== category) return false;
      if (!needle) return true;
      return (
        entry.name.toLowerCase().includes(needle) ||
        entry.description.toLowerCase().includes(needle) ||
        entry.slug.toLowerCase().includes(needle)
      );
    });
  }, [catalog.data, query, category]);

  if (catalog.isError) {
    return (
      <ErrorState
        title="Could not load the marketplace"
        description="The orchestration service did not respond. Your installed integrations are unaffected."
        onRetry={() => void catalog.refetch()}
      />
    );
  }

  if (catalog.isLoading && !catalog.data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-40 rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search integrations"
            aria-label="Search integrations"
            className="pl-9"
          />
        </div>
        <RegisterCustomServerDialog workspaceId={workspaceId} />
      </div>

      <FilterGroup
        label="Filter integrations by category"
        value={category}
        onValueChange={setCategory}
        options={CATEGORY_FILTERS}
      />

      {visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No integrations match"
          description="Try a different search term, or clear the category filter."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((entry) => (
            <CatalogCard
              key={entry.id}
              workspaceId={workspaceId}
              entry={entry}
              isInstalled={installedServerIds.has(entry.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CatalogCard({
  workspaceId,
  entry,
  isInstalled,
}: {
  workspaceId: string;
  entry: McpServer;
  isInstalled: boolean;
}): React.JSX.Element {
  const install = useInstallFromCatalog(workspaceId);
  const availability = AVAILABILITY[entry.availability];
  const transport = TRANSPORTS[entry.transport];
  const CategoryIcon = CATEGORY_ICONS[entry.category] ?? Server;

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
        >
          <CategoryIcon className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-medium">{entry.name}</h3>
            <StatusBadge tone={availability.tone}>{availability.label}</StatusBadge>
          </div>
          <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{entry.description}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="gap-1.5">
          <transport.icon className="size-3" aria-hidden="true" />
          {transport.label}
        </Badge>
        {entry.required_credentials.length > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              {/* Focusable so the credential list is reachable without a
                  pointer — a tooltip on an inert span is invisible to
                  keyboard users, and this is information they need
                  before handing over a secret. */}
              <Badge variant="secondary" tabIndex={0}>
                {entry.required_credentials.length}{" "}
                {entry.required_credentials.length === 1 ? "credential" : "credentials"}
              </Badge>
            </TooltipTrigger>
            {/* Shown before the user commits, not after — they should
                know what they are being asked to hand over. */}
            <TooltipContent>
              Needs: {entry.required_credentials.join(", ")}
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      {!entry.is_installable && (
        <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {availability.summary}
        </p>
      )}

      <div className="mt-auto flex items-center gap-2 pt-1">
        {isInstalled ? (
          <Button variant="secondary" size="sm" disabled className="gap-1.5">
            <Check className="size-3.5" aria-hidden="true" />
            Installed
          </Button>
        ) : (
          <Button
            size="sm"
            className="gap-1.5"
            disabled={!entry.is_installable || install.isPending}
            onClick={() => install.mutate(entry.id)}
          >
            <Download className="size-3.5" aria-hidden="true" />
            {entry.is_installable ? "Install" : "Unavailable"}
          </Button>
        )}
        {entry.documentation_url && (
          <Button variant="ghost" size="sm" asChild className="gap-1.5">
            <a href={entry.documentation_url} target="_blank" rel="noreferrer noopener">
              Docs
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </a>
          </Button>
        )}
      </div>
    </Card>
  );
}
