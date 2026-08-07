"use client";

import { BookText, Bot, BookOpen, Moon, Plus, Store, Sun, Users2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import * as React from "react";

import { hrefFor, NAV_SECTIONS } from "@/lib/navigation";
import { KIND_LABELS, hrefForHit, type SearchKind } from "@/lib/search/kinds";
import { type DocsSearchEntry, searchDocs } from "@/lib/docs/match";
import { useWorkspaceSearch } from "@/lib/queries/search";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";

const KIND_ICONS: Record<SearchKind, React.ComponentType<{ className?: string }>> = {
  agent: Bot,
  knowledge_base: BookOpen,
  team: Users2,
  listing: Store,
};

/**
 * ⌘K / Ctrl+K palette — the keyboard-first path to every route, and now
 * to the workspace's actual contents.
 *
 * Three sources, in the order a user is most likely to want them:
 *
 * 1. **Their own work** — agents, knowledge bases, teams, and the
 *    catalog — from the search API, which is the only source that has
 *    to go to the server, because it is the only one that is
 *    tenant-scoped.
 * 2. **Routes**, from the shared `NAV_SECTIONS` model, so a route added
 *    to the sidebar is searchable here with no second edit. Deep routes
 *    hidden from the sidebar (Documents, API keys, Security) are
 *    intentionally still reachable.
 * 3. **Documentation**, matched in the browser against an index that
 *    shipped with the page — the guides are public and identical for
 *    everyone, so there is nothing to fetch.
 */
export function CommandPalette({
  workspaceId,
  docsIndex = [],
}: {
  workspaceId: string;
  docsIndex?: readonly DocsSearchEntry[];
}): React.JSX.Element {
  const router = useRouter();
  const { setTheme, resolvedTheme } = useTheme();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((previous) => !previous);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const run = React.useCallback((action: () => void) => {
    setOpen(false);
    action();
  }, []);

  // Reopening the palette should start fresh. Leaving the previous
  // query in place means ⌘K shows stale results for something the user
  // searched for ten minutes ago.
  const onOpenChange = React.useCallback((next: boolean) => {
    setOpen(next);
    if (!next) setQuery("");
  }, []);

  const { data: results, isFetching } = useWorkspaceSearch(workspaceId, query);
  const docsResults = React.useMemo(
    () => searchDocs(docsIndex, query, 4),
    [docsIndex, query],
  );

  const remoteGroups = (results?.groups ?? []).filter((group) => group.hits.length > 0);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder="Search agents, docs, pages and actions…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>
          {isFetching ? "Searching…" : "No matches."}
        </CommandEmpty>

        {/*
          Workspace results first: someone who opens ⌘K and types a name
          is looking for a thing, not a page. Groups arrive already
          ranked and capped by the server.
        */}
        {remoteGroups.map((group) => {
          const Icon = KIND_ICONS[group.kind];
          return (
            <CommandGroup key={group.kind} heading={KIND_LABELS[group.kind]}>
              {group.hits.map((hit) => (
                <CommandItem
                  key={`${group.kind}-${hit.id}`}
                  // The raw query is appended so cmdk's own fuzzy filter
                  // always keeps these visible. They were matched by
                  // Postgres full-text search, which finds things
                  // ("sal" → "Sales qualifier") that a client-side
                  // substring filter would then hide again.
                  value={`${hit.title} ${hit.subtitle ?? ""} ${query}`}
                  onSelect={() =>
                    run(() => router.push(hrefForHit(workspaceId, group.kind, hit.id)))
                  }
                >
                  <Icon />
                  <span className="truncate">{hit.title}</span>
                  {hit.subtitle && (
                    <span className="ml-2 truncate text-xs text-muted-foreground">
                      {hit.subtitle}
                    </span>
                  )}
                </CommandItem>
              ))}
              {group.has_more && (
                <CommandItem disabled value={`more-${group.kind} ${query}`}>
                  <span className="text-xs text-muted-foreground">
                    More {KIND_LABELS[group.kind].toLowerCase()} match — keep typing to narrow.
                  </span>
                </CommandItem>
              )}
            </CommandGroup>
          );
        })}

        {docsResults.length > 0 && (
          <CommandGroup heading="Documentation">
            {docsResults.map((entry) => (
              <CommandItem
                key={entry.slug}
                value={`${entry.title} ${entry.summary} ${query}`}
                onSelect={() => run(() => router.push(`/docs/${entry.slug}`))}
              >
                <BookText />
                <span className="truncate">{entry.title}</span>
                <span className="ml-2 truncate text-xs text-muted-foreground">
                  {entry.pillarName}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {(remoteGroups.length > 0 || docsResults.length > 0) && <CommandSeparator />}

        <CommandGroup heading="Go to">
          {NAV_SECTIONS.map((item) => {
            const Icon = item.icon;
            return (
              <CommandItem
                key={item.segment || "dashboard"}
                // `value` drives cmdk's fuzzy match — including the
                // description means "retrieval" finds Knowledge.
                value={`${item.label} ${item.description}`}
                onSelect={() => run(() => router.push(hrefFor(workspaceId, item.segment)))}
              >
                <Icon />
                <span>{item.label}</span>
                {item.pending && (
                  <span className="ml-auto text-[10px] tracking-wide text-muted-foreground uppercase">
                    Soon
                  </span>
                )}
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Actions">
          <CommandItem
            value="New agent create build"
            onSelect={() => run(() => router.push(hrefFor(workspaceId, "agents")))}
          >
            <Plus />
            <span>New agent</span>
          </CommandItem>
          <CommandItem
            value="New knowledge base upload documents"
            onSelect={() => run(() => router.push(hrefFor(workspaceId, "knowledge")))}
          >
            <Plus />
            <span>New knowledge base</span>
          </CommandItem>
          <CommandItem
            value="Toggle theme dark light appearance"
            onSelect={() => run(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"))}
          >
            {resolvedTheme === "dark" ? <Sun /> : <Moon />}
            <span>Switch to {resolvedTheme === "dark" ? "light" : "dark"} theme</span>
            <CommandShortcut>⌘K</CommandShortcut>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
