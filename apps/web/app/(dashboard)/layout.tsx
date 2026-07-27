import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

/**
 * Real, verified session check (not the cookie-presence check
 * middleware.ts does) — CLAUDE.md §6: middleware stays thin, the
 * protected route group's layout does the actual verification.
 *
 * Deliberately chrome-free: `/dashboard` itself is the workspace picker,
 * which has no workspace to build a shell around. The topbar and sidebar
 * live one level down in `[workspaceId]/layout.tsx`, where a workspace
 * context actually exists.
 */
export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<React.JSX.Element> {
  const session = await auth.api.getSession({ headers: await headers() });

  if (!session) {
    redirect("/login");
  }

  return <div className="min-h-screen bg-background">{children}</div>;
}
