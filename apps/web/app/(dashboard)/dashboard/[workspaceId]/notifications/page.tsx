import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";

export default function NotificationsPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Notifications"
        description="Failed runs, quota thresholds, and workspace invitations."
      />
      <IntegrationPending feature="notifications" />
    </div>
  );
}

export const metadata = {
  title: "Notifications · AgentVerse",
};
