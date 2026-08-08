import Link from "next/link";
import * as React from "react";

import { listAgents } from "@/lib/api/agents";
import { listCategories, listMyListings } from "@/lib/api/marketplace";

import { CreateListingDialog } from "@/components/marketplace/create-listing-dialog";
import { MyListingsTable } from "@/components/marketplace/my-listings-table";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

/**
 * The publisher console — this workspace's listings in every status,
 * including the drafts and rejections the public catalog never returns.
 */
export default async function MyListingsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const [listings, categories, agents] = await Promise.all([
    listMyListings(workspaceId),
    listCategories(),
    // Needed by the publish-version dialog: a listing version is frozen
    // from one of this workspace's published agents.
    listAgents(workspaceId),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Your listings"
        description="Drafts, listings in review, and everything you have published. Only your workspace sees this page."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild>
              <Link href={`/dashboard/${workspaceId}/marketplace`}>Browse catalog</Link>
            </Button>
            {listings.length > 0 && (
              <CreateListingDialog workspaceId={workspaceId} categories={categories} />
            )}
          </div>
        }
      />
      <MyListingsTable
        workspaceId={workspaceId}
        categories={categories}
        agents={agents}
        initialListings={listings}
      />
    </div>
  );
}

export const metadata = {
  title: "Your listings · AgentVerse",
};
