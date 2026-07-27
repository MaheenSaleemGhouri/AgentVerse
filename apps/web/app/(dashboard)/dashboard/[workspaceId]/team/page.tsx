import { notFound } from "next/navigation";

import { listMembers, listMyWorkspaces } from "@/lib/api/workspaces";

import { PageHeader } from "@/components/patterns/page-header";
import { InviteMemberDialog } from "@/components/team/invite-member-dialog";
import { MembersTable } from "@/components/team/members-table";

export default async function TeamPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const [workspaces, members] = await Promise.all([
    listMyWorkspaces(),
    listMembers(workspaceId),
  ]);

  const current = workspaces.find((workspace) => workspace.id === workspaceId);
  if (!current) notFound();

  // Only owners and admins may change membership. The API enforces this
  // regardless (Rule 6 — every browser-side control is re-enforced
  // server-side); hiding the controls just avoids offering an action
  // that would be rejected.
  const canManage = current.role === "owner" || current.role === "admin";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Team"
        description="Workspace members and what each of them can do."
        actions={canManage ? <InviteMemberDialog workspaceId={workspaceId} /> : undefined}
      />
      <MembersTable
        workspaceId={workspaceId}
        initialMembers={members}
        viewerRole={current.role}
        canManage={canManage}
      />
    </div>
  );
}

export const metadata = {
  title: "Team · AgentVerse",
};
