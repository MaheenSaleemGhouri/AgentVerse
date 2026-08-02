"use client";

import { Building2, Check, ChevronsUpDown, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import type { Workspace } from "@/lib/api/workspaces";
import { initialsFrom } from "@/lib/format";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/**
 * Replaces the native `<select>` the first pass used.
 *
 * A workspace list can grow past what a select comfortably handles, and
 * the combobox gives type-to-filter for free while keeping Radix's
 * roving focus and Esc handling — behaviour a styled div would have had
 * to reimplement.
 */
export function WorkspaceSwitcher({
  workspaces,
  activeWorkspaceId,
}: {
  workspaces: Workspace[];
  activeWorkspaceId: string;
}): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const active = workspaces.find((workspace) => workspace.id === activeWorkspaceId);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          role="combobox"
          aria-expanded={open}
          aria-label="Switch workspace"
          className="h-9 max-w-56 justify-start gap-2 px-2"
        >
          <span
            aria-hidden="true"
            className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary text-[10px] font-semibold text-primary-foreground"
          >
            {initialsFrom(active?.name ?? "AV")}
          </span>
          <span className="truncate text-sm font-medium">{active?.name ?? "Select workspace"}</span>
          <ChevronsUpDown className="ml-auto size-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <Command>
          <CommandInput placeholder="Find workspace…" />
          <CommandList>
            <CommandEmpty>No workspace found.</CommandEmpty>
            <CommandGroup heading="Workspaces">
              {workspaces.map((workspace) => (
                <CommandItem
                  key={workspace.id}
                  value={workspace.name}
                  onSelect={() => {
                    setOpen(false);
                    router.push(`/dashboard/${workspace.id}`);
                  }}
                >
                  <span
                    aria-hidden="true"
                    className="flex size-5 shrink-0 items-center justify-center rounded bg-muted text-[9px] font-semibold text-muted-foreground"
                  >
                    {initialsFrom(workspace.name)}
                  </span>
                  <span className="truncate">{workspace.name}</span>
                  {workspace.id === activeWorkspaceId && (
                    <Check className="ml-auto size-4 text-primary" />
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup>
              <CommandItem
                value="Create new workspace"
                onSelect={() => {
                  setOpen(false);
                  router.push("/dashboard");
                }}
              >
                <Plus />
                <span>New workspace</span>
              </CommandItem>
              <CommandItem
                value="Organizations"
                onSelect={() => {
                  setOpen(false);
                  router.push("/organizations");
                }}
              >
                <Building2 />
                <span>Organizations</span>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
