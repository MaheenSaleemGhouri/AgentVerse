import { PageHeader } from "@/components/patterns/page-header";
import { SettingsNav } from "@/components/settings/settings-nav";

export default async function SettingsLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Workspace configuration, your profile, credentials, and appearance."
      />
      <div className="flex flex-col gap-6 lg:flex-row lg:gap-10">
        <SettingsNav workspaceId={workspaceId} />
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
