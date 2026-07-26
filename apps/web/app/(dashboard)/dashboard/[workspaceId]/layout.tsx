import { Sidebar } from "@/components/dashboard/sidebar";

/**
 * Adds the AVDS fixed sidebar once a workspace is selected — the
 * top-level `/dashboard` (workspace picker, no `workspaceId` yet) stays
 * outside this layout and keeps the plain shell from the parent
 * `(dashboard)/layout.tsx`.
 */
export default async function WorkspaceShellLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  return (
    <div className="flex flex-1 gap-6">
      <Sidebar workspaceId={workspaceId} />
      <div className="flex-1 py-2">{children}</div>
    </div>
  );
}
