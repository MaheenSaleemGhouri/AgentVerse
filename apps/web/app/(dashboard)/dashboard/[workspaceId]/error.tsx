"use client";

import * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";

/**
 * Catches render/fetch failures inside a workspace route.
 *
 * `digest` is surfaced because it is the only handle that ties what the
 * user saw to a specific server-side log entry — a generic apology with
 * nothing to quote makes a support conversation guesswork.
 */
export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.JSX.Element {
  React.useEffect(() => {
    console.error("workspace_route_error", error);
  }, [error]);

  return (
    <div className="py-12">
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
  );
}
