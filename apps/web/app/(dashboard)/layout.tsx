import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

import { SignOutButton } from "./sign-out-button";

/**
 * Real, verified session check (not the cookie-presence check
 * middleware.ts does) — CLAUDE.md §6: middleware stays thin, the
 * protected route group's layout does the actual verification.
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

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-neutral-200 px-6 py-3 dark:border-neutral-800">
        <span className="text-sm font-semibold">AgentVerse</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-neutral-500">{session.user.email}</span>
          <SignOutButton />
        </div>
      </header>
      <main className="flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
