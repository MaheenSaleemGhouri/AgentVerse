import { getAuditActivity, listAuditLogs } from "@/lib/api/audit-logs";

import { AuditActivityGraph } from "@/components/audit-logs/audit-activity-graph";
import { AuditExportButton } from "@/components/audit-logs/audit-export-button";
import { AuditLogTable } from "@/components/audit-logs/audit-log-table";
import { PageHeader } from "@/components/patterns/page-header";

/** Matches the API's own default window, defined once so the graph's
 *  copy and the query it describes can never disagree. */
const ACTIVITY_DAYS = 30;

export default async function AuditLogsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  // Both reads are admin-gated upstream, which this route already is —
  // a member never reaches it.
  const [initialPage, activity] = await Promise.all([
    listAuditLogs(workspaceId, { limit: 50 }),
    getAuditActivity(workspaceId, ACTIVITY_DAYS),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit logs"
        description="An append-only record of who did what in this workspace."
        actions={<AuditExportButton workspaceId={workspaceId} />}
      />
      <AuditActivityGraph activity={activity} days={ACTIVITY_DAYS} />
      <AuditLogTable workspaceId={workspaceId} initialPage={initialPage} />
    </div>
  );
}

export const metadata = {
  title: "Audit logs · AgentVerse",
};
