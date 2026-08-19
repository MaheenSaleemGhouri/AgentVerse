import { Share2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";

/**
 * Deep-links into the existing generic `ResourcePermissionsPanel` on the
 * Team page rather than building a bespoke sharing UI — `resource_type`
 * is unrestricted free text (Increment 6), so `"workflow"` already works
 * with zero backend change (docs/adr/0016, Area E). The panel reads
 * these two query params to pre-fill and auto-open its grant dialog.
 */
export function ShareWorkflowButton({
  workspaceId,
  workflowId,
}: {
  workspaceId: string;
  workflowId: string;
}): React.JSX.Element {
  return (
    <Button variant="outline" asChild>
      <Link
        href={`/dashboard/${workspaceId}/team?resourceType=workflow&resourceId=${workflowId}#resource-permissions`}
      >
        <Share2 />
        Share
      </Link>
    </Button>
  );
}
