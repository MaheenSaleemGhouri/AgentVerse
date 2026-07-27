"use client";

import { Moon, Plus, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import * as React from "react";

import { hrefFor, NAV_SECTIONS } from "@/lib/navigation";

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

/**
 * ⌘K / Ctrl+K palette — the keyboard-first path to every route.
 *
 * Navigation entries come from the shared `NAV_SECTIONS` model, so a
 * route added to the sidebar is searchable here with no second edit.
 * Deep routes hidden from the sidebar (Documents, API keys, Security)
 * are intentionally still reachable here.
 */
export function CommandPalette({ workspaceId }: { workspaceId: string }): React.JSX.Element {
  const router = useRouter();
  const { setTheme, resolvedTheme } = useTheme();
  const [open, setOpen] = React.useState(false);

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

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search pages and actions…" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

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
