"use client";

import { useRouter } from "next/navigation";

import type { Workspace } from "@/lib/api/workspaces";

export function WorkspaceSwitcher({
  workspaces,
  activeWorkspaceId,
}: {
  workspaces: Workspace[];
  activeWorkspaceId: string;
}): React.JSX.Element {
  const router = useRouter();

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="sr-only">Switch workspace</span>
      <select
        value={activeWorkspaceId}
        onChange={(event) => router.push(`/dashboard/${event.target.value}`)}
        className="rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
      >
        {workspaces.map((workspace) => (
          <option key={workspace.id} value={workspace.id}>
            {workspace.name}
          </option>
        ))}
      </select>
    </label>
  );
}
