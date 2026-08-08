import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { listMyWorkspaces } from "@/lib/api/workspaces";
import { auth } from "@/lib/auth";
import { buildDocsSearchIndex } from "@/lib/docs/search-index";

import { AssistantLauncher } from "@/components/assistant/assistant-launcher";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";

/**
 * The workspace shell — topbar + fixed AVDS sidebar around every
 * workspace-scoped route.
 *
 * Both the session and the workspace list are fetched server-side and
 * passed down as props (CLAUDE.md §6: initial data is server-fetched),
 * so the shell renders complete on first paint rather than flashing an
 * empty switcher while a client request resolves.
 */
export default async function WorkspaceShellLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/login");
  }

  const workspaces = await listMyWorkspaces();

  // A workspace id the caller is not a member of must not render a shell
  // that implies it exists — every child fetch would 404 anyway, and
  // showing the chrome first would confirm it by inference (Rule 11).
  if (!workspaces.some((workspace) => workspace.id === workspaceId)) {
    redirect("/dashboard");
  }

  // Read from disk on the server so the ⌘K palette can match guides
  // without a request. Public content, identical for every user — there
  // is nothing here to scope to the workspace.
  const docsIndex = await buildDocsSearchIndex();

  return (
    <div className="flex min-h-screen flex-col">
      <Topbar
        workspaces={workspaces}
        activeWorkspaceId={workspaceId}
        userEmail={session.user.email}
        userName={session.user.name}
        docsIndex={docsIndex}
      />
      <div className="flex flex-1">
        <Sidebar workspaceId={workspaceId} />
        <main className="min-w-0 flex-1 px-6 py-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </div>
      <AssistantLauncher workspaceId={workspaceId} />
    </div>
  );
}
