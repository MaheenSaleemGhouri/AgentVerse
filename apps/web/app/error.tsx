"use client";

import * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";

/**
 * Catches render/fetch failures outside `(dashboard)`, which had no
 * boundary of its own before this — an uncaught error on the marketing
 * or docs surfaces fell through to Next.js's unstyled default. Mirrors
 * `app/(dashboard)/dashboard/[workspaceId]/error.tsx`'s pattern.
 */
export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.JSX.Element {
  React.useEffect(() => {
    console.error("root_route_error", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
      <div className="w-full max-w-md">
        <ErrorState
          title="This page did not load"
          description={
            error.digest
              ? `Something failed while rendering. Reference ${error.digest} if you report this.`
              : "Something failed while rendering this page. Retrying often resolves it."
          }
          onRetry={reset}
        />
      </div>
    </main>
  );
}
