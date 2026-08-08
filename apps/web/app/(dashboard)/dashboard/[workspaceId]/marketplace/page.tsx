import Link from "next/link";
import * as React from "react";

import { browseListings, listCategories } from "@/lib/api/marketplace";

import { MarketplaceCatalog } from "@/components/marketplace/marketplace-catalog";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";

/**
 * The catalog.
 *
 * The first page and the category list are server-fetched so the grid
 * paints complete rather than flashing a skeleton (CLAUDE.md §6);
 * `MarketplaceCatalog` seeds the TanStack Query cache with them and
 * takes over for filtering and paging.
 */
export default async function MarketplacePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}): Promise<React.JSX.Element> {
  const { workspaceId } = await params;
  const [categories, firstPage] = await Promise.all([
    listCategories(),
    browseListings({ sort: "popular", page: 1 }),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Marketplace"
        description="Install a first-party template or a community agent — it becomes a normal agent in your workspace, yours to edit."
        actions={
          <Button variant="outline" asChild>
            <Link href={`/dashboard/${workspaceId}/marketplace/my-listings`}>Your listings</Link>
          </Button>
        }
      />
      <MarketplaceCatalog
        workspaceId={workspaceId}
        categories={categories}
        initialPage={firstPage}
      />
    </div>
  );
}

export const metadata = {
  title: "Marketplace · AgentVerse",
};
