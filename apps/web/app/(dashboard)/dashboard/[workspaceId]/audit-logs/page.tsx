import { listAuditLogs } from "@/lib/api/audit-logs";

import { AuditLogTable } from "@/components/audit-logs/audit-log-table";
import { PageHeader } from "@/components/patterns/page-header";

export default async function AuditLogsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const initialPage = await listAuditLogs(workspaceId, { limit: 50 });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit logs"
        description="An append-only record of who did what in this workspace."
      />
      <AuditLogTable workspaceId={workspaceId} initialPage={initialPage} />
    </div>
  );
}

export const metadata = {
  title: "Audit logs · AgentVerse",
};
