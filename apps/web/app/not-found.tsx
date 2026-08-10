import Link from "next/link";

import { AgentVerseMascot } from "@/components/brand/agentverse-mascot";
import { Button } from "@/components/ui/button";

/**
 * The one 404 every route outside `(dashboard)` falls back to — the
 * marketing/auth/docs/pricing surfaces had none before this (the
 * workspace route group has its own, more specific version at
 * `app/(dashboard)/dashboard/[workspaceId]/not-found.tsx`).
 */
export default function RootNotFound(): React.JSX.Element {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-6 py-16 text-center">
      <AgentVerseMascot pose="thinking" className="h-32 w-auto" />
      <div className="space-y-2">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">
          Page not found
        </h1>
        <p className="mx-auto max-w-sm text-sm text-muted-foreground">
          The page you&apos;re looking for doesn&apos;t exist, or it moved.
        </p>
      </div>
      <Button asChild>
        <Link href="/">Back to AgentVerse</Link>
      </Button>
    </main>
  );
}
