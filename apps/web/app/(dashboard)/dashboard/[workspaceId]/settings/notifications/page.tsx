import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";

export default function NotificationPreferencesPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Notifications"
        description="Choose which notification categories reach you by email vs. in-app only."
      />
      <IntegrationPending feature="notificationPreferences" />
    </div>
  );
}

export const metadata = {
  title: "Notification preferences · AgentVerse",
};
