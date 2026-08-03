import { ArrowLeft } from "lucide-react";
import Link from "next/link";

/**
 * Organizations sit above workspaces (ADR-0011) — this route group is
 * deliberately chrome-free of the workspace `[workspaceId]/layout.tsx`
 * sidebar/topbar, the same way `/dashboard` (the workspace picker) is,
 * since neither has a workspace to build that chrome around.
 */
export default function OrganizationsLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-3">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to AgentVerse
        </Link>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-8">{children}</main>
    </div>
  );
}
