import { FileQuestion } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/patterns/empty-state";
import { Button } from "@/components/ui/button";

/**
 * Rendered for a resource that either does not exist or belongs to
 * another workspace — the API returns 404 for both, deliberately, so
 * this copy must not imply the resource exists somewhere else.
 */
export default function WorkspaceNotFound(): React.JSX.Element {
  return (
    <div className="py-12">
      <EmptyState
        icon={FileQuestion}
        mascot="thinking"
        title="Not found"
        description="This resource doesn't exist, or it isn't part of a workspace you have access to."
        action={
          <Button asChild>
            <Link href="/dashboard">Back to your workspaces</Link>
          </Button>
        }
      />
    </div>
  );
}
