import { notFound } from "next/navigation";

import { listMembers, listMyWorkspaces } from "@/lib/api/workspaces";
import { WorkspaceSwitcher } from "@/app/(dashboard)/workspace-switcher/workspace-switcher";

import { MembersPanel } from "./members-panel";

export default async function WorkspaceDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const workspaces = await listMyWorkspaces();
  const current = workspaces.find((workspace) => workspace.id === workspaceId);

  if (!current) {
    // Membership lookup already failed server-side in listMembers below
    // if this were a workspace the user isn't in — this specific check
    // covers a stale/bookmarked link to a workspace no longer listed.
    notFound();
  }

  const members = await listMembers(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{current.name}</h1>
          <p className="text-sm text-neutral-500">Your role: {current.role}</p>
        </div>
        <WorkspaceSwitcher workspaces={workspaces} activeWorkspaceId={workspaceId} />
      </div>

      <MembersPanel workspaceId={workspaceId} members={members} viewerRole={current.role} />
    </div>
  );
}
