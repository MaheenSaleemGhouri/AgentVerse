import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { RuntimeView } from "@/components/integrations/runtime-view";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

/**
 * MCP runtime — every tool call across the workspace.
 *
 * Deliberately *not* a second marketplace: installing and configuring
 * lives on `/integrations`, and two screens offering the same install
 * button would leave users unsure which one is authoritative. This one
 * answers a different question — what have my agents actually been
 * doing, and what got refused.
 */
export default async function McpPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="MCP runtime"
        description="Every tool call your agents made through an integration, including the ones that were refused."
        actions={
          <Button variant="outline" asChild>
            <Link href={`/dashboard/${workspaceId}/integrations`}>
              Manage integrations
              <ArrowRight />
            </Link>
          </Button>
        }
      />

      <RuntimeView workspaceId={workspaceId} />
    </div>
  );
}

export const metadata = {
  title: "MCP runtime · AgentVerse",
};
