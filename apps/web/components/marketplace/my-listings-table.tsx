"use client";

import { EyeOff, PackagePlus, Send } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { Category, Listing } from "@/lib/marketplace/types";
import { formatNumber, formatRelativeTime } from "@/lib/format";
import { useMyListings, useSubmitListing, useUnlistListing } from "@/lib/queries/marketplace";

import { CreateListingDialog } from "@/components/marketplace/create-listing-dialog";
import { ListingStatusBadge } from "@/components/marketplace/listing-status-badge";
import { PublishVersionDialog } from "@/components/marketplace/publish-version-dialog";
import { EmptyState } from "@/components/patterns/empty-state";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/**
 * The publisher console.
 *
 * A table rather than the catalog's card grid, on purpose: a publisher
 * is not browsing, they are checking status across a handful of rows and
 * acting on one. Status, version and install count belong in scannable
 * columns.
 *
 * This is the only surface that shows drafts and rejections — the public
 * catalog never returns them.
 */
export function MyListingsTable({
  workspaceId,
  categories,
  agents,
  initialListings,
}: {
  workspaceId: string;
  categories: Category[];
  agents: Agent[];
  initialListings: Listing[];
}): React.JSX.Element {
  const { data: listings = [] } = useMyListings(workspaceId, initialListings);

  if (listings.length === 0) {
    return (
      <EmptyState
        icon={PackagePlus}
        title="You have not published anything"
        description="A listing is a frozen copy of one of your agents that other workspaces can install. It stays a private draft until you submit it and it is approved."
        action={<CreateListingDialog workspaceId={workspaceId} categories={categories} />}
      />
    );
  }

  return (
    <Card className="p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Listing</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Version</TableHead>
            <TableHead className="text-right">Installs</TableHead>
            <TableHead>Published</TableHead>
            <TableHead className="w-1">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {listings.map((listing) => (
            <ListingRow
              key={listing.slug}
              workspaceId={workspaceId}
              listing={listing}
              agents={agents}
            />
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

function ListingRow({
  workspaceId,
  listing,
  agents,
}: {
  workspaceId: string;
  listing: Listing;
  agents: Agent[];
}): React.JSX.Element {
  const [confirmUnlist, setConfirmUnlist] = React.useState(false);
  const submit = useSubmitListing(workspaceId);
  const unlist = useUnlistListing(workspaceId);

  // Submitting is only meaningful from a state review can move forward
  // from. A published listing has nowhere to go; a pending one is
  // already there.
  const canSubmit = listing.status === "draft" || listing.status === "rejected";
  const canUnlist = listing.status === "published";

  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/dashboard/${workspaceId}/marketplace/${listing.slug}`}
          className="font-medium hover:underline"
        >
          {listing.title}
        </Link>
        <p className="line-clamp-1 text-xs text-muted-foreground">{listing.summary}</p>
      </TableCell>
      <TableCell>
        <ListingStatusBadge status={listing.status} />
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {/* Zero, not null, means "no version yet" — and an em dash says
            that more clearly to a scanning eye than "v0" would. */}
        {listing.latest_version === 0 ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          `v${listing.latest_version}`
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {formatNumber(listing.install_count)}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {listing.published_at === null ? (
          <span>Not published</span>
        ) : (
          <time dateTime={listing.published_at}>
            {formatRelativeTime(listing.published_at)}
          </time>
        )}
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-2">
          <PublishVersionDialog workspaceId={workspaceId} listing={listing} agents={agents} />

          {canSubmit && (
            <Button
              variant="outline"
              size="sm"
              disabled={submit.isPending}
              onClick={() => submit.mutate(listing.slug)}
            >
              <Send className="size-4" />
              Submit
            </Button>
          )}

          {canUnlist && (
            <Button variant="ghost" size="sm" onClick={() => setConfirmUnlist(true)}>
              <EyeOff className="size-4" />
              Unlist
            </Button>
          )}
        </div>

        {/* Unlisting is public and hard to undo in the sense that
            matters — installs stop. Confirmation friction scales with
            reversibility, so this one gets an explicit dialog while
            Submit does not. */}
        <AlertDialog open={confirmUnlist} onOpenChange={setConfirmUnlist}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Unlist “{listing.title}”?</AlertDialogTitle>
              <AlertDialogDescription>
                It disappears from the catalog and from search, and nobody new can install it.
                Workspaces that already installed it keep working — an install is a copy, not a
                subscription.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep it listed</AlertDialogCancel>
              <AlertDialogAction onClick={() => unlist.mutate(listing.slug)}>
                Unlist
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </TableCell>
    </TableRow>
  );
}
