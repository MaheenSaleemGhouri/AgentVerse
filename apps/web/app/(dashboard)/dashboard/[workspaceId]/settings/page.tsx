import { notFound } from "next/navigation";

import { getWorkspaceSettings } from "@/lib/api/workspace-settings";
import { listMembers, listMyWorkspaces } from "@/lib/api/workspaces";
import { formatDateTime } from "@/lib/format";
import { ROLE_DESCRIPTIONS } from "@/lib/roles";

import { CopyButton } from "@/components/patterns/copy-button";
import { StatusBadge } from "@/components/patterns/status-badge";
import { WorkspaceSettingsForm } from "@/components/settings/workspace-settings-form";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default async function WorkspaceSettingsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const [workspaces, members, settings] = await Promise.all([
    listMyWorkspaces(),
    listMembers(workspaceId),
    getWorkspaceSettings(workspaceId),
  ]);
  const current = workspaces.find((workspace) => workspace.id === workspaceId);
  if (!current) notFound();

  const canManage = current.role === "owner" || current.role === "admin";

  return (
    <div className="max-w-2xl space-y-6">
      <Card className="gap-4 p-6">
        <div>
          <h2 className="font-medium">Workspace</h2>
          <p className="text-sm text-muted-foreground">
            Identity and tenancy root — every agent, knowledge base, and run belongs to it.
          </p>
        </div>
        <Separator />
        <Field label="Name" value={current.name} />
        <Field label="Workspace ID" value={current.id} mono copyable />
        <Field label="Created" value={formatDateTime(current.created_at)} />
        <Field label="Members" value={`${members.length}`} />
      </Card>

      <Card className="gap-4 p-6">
        <div>
          <h2 className="font-medium">Your access</h2>
          <p className="text-sm text-muted-foreground">
            What you can do in this workspace, enforced server-side on every request.
          </p>
        </div>
        <Separator />
        <div className="flex items-start gap-3">
          <StatusBadge tone={current.role === "owner" ? "brand" : "info"}>
            <span className="capitalize">{current.role}</span>
          </StatusBadge>
          <p className="text-sm text-muted-foreground">{ROLE_DESCRIPTIONS[current.role]}</p>
        </div>
      </Card>

      <WorkspaceSettingsForm
        workspaceId={workspaceId}
        initialSettings={settings}
        canManage={canManage}
      />
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  copyable,
}: {
  label: string;
  value: string;
  mono?: boolean;
  copyable?: boolean;
}): React.JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-sm text-muted-foreground">{label}</span>
      <span className={mono ? "min-w-0 flex-1 truncate font-mono text-sm" : "min-w-0 flex-1 text-sm"}>
        {value}
      </span>
      {copyable && <CopyButton value={value} label={`Copy ${label}`} size="icon-xs" />}
    </div>
  );
}
