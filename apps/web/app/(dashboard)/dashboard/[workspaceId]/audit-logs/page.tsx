import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { Card } from "@/components/ui/card";

const RECORDED_EVENTS = [
  { label: "Authentication", detail: "Sign-in, sign-out, and failed attempts" },
  { label: "Permission changes", detail: "Role grants, revocations, and denials on sensitive actions" },
  { label: "Destructive operations", detail: "Agent, knowledge base, and member deletion" },
  { label: "Credential lifecycle", detail: "API keys issued and revoked" },
];

export default function AuditLogsPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit logs"
        description="An append-only record of who did what in this workspace."
      />

      <IntegrationPending feature="auditLogs">
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">What will be recorded</h2>
          <Card className="gap-0 divide-y divide-border p-0">
            {RECORDED_EVENTS.map((event) => (
              <div key={event.label} className="px-5 py-3.5">
                <p className="text-sm font-medium">{event.label}</p>
                <p className="text-sm text-muted-foreground">{event.detail}</p>
              </div>
            ))}
          </Card>
          <p className="text-xs text-muted-foreground">
            Written from the enforcement point so they cannot be bypassed, and never containing the
            credential itself.
          </p>
        </section>
      </IntegrationPending>
    </div>
  );
}

export const metadata = {
  title: "Audit logs · AgentVerse",
};
