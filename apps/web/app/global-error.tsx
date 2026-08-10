"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";

/**
 * Catches a failure in the root layout itself — the one error boundary
 * that must render its own `<html>`/`<body>`, since it replaces the
 * layout that would normally provide them (Next.js App Router
 * convention). Deliberately minimal and dependency-light: this is the
 * last line of defense, so it does not lean on `Providers` (theme/query
 * client) or any component that could itself be implicated in the crash
 * it is reporting.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.JSX.Element {
  React.useEffect(() => {
    console.error("global_root_error", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="bg-background text-foreground antialiased">
        <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 py-16 text-center">
          <h1 className="text-xl font-semibold tracking-tight">AgentVerse hit a snag</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            {error.digest
              ? `Something failed at the application level. Reference ${error.digest} if you report this.`
              : "Something failed at the application level. Reloading usually resolves it."}
          </p>
          <Button onClick={reset}>Try again</Button>
        </main>
      </body>
    </html>
  );
}
