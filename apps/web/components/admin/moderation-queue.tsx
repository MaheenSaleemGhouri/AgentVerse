"use client";

import { CheckCircle2, ExternalLink, ShieldCheck, Star, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  approveListingAction,
  featureListingAction,
  listModerationQueueAction,
  rejectListingAction,
} from "@/lib/api/actions";
import type { ModerationListing } from "@/lib/admin/types";
import { EmptyState } from "@/components/patterns/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * The moderation queue.
 *
 * Oldest first, as the API returns it — a queue sorted newest-first
 * starves its tail, and the listing nobody looked at yesterday is the
 * one most in need of looking at today.
 *
 * A decision is not undoable from here: an approved listing goes to
 * every customer's catalog, so approval and rejection each get an
 * explicit confirmation step rather than a one-click row action.
 */
export function ModerationQueue({
  initialQueue,
}: {
  initialQueue: ModerationListing[];
}): React.JSX.Element {
  const [queue, setQueue] = React.useState(initialQueue);
  const [decision, setDecision] = React.useState<{
    listing: ModerationListing;
    kind: "approve" | "reject";
  } | null>(null);
  const [note, setNote] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      setQueue(await listModerationQueueAction());
    } catch {
      setError("Could not refresh the queue.");
    }
  }, []);

  const decide = React.useCallback(async () => {
    if (decision === null) return;

    setPending(true);
    setError(null);
    try {
      if (decision.kind === "approve") {
        await approveListingAction(decision.listing.id, note);
      } else {
        await rejectListingAction(decision.listing.id, note);
      }
      setDecision(null);
      setNote("");
      await refresh();
    } catch {
      setError(
        decision.kind === "reject" && note.trim() === ""
          ? "A rejection must say why, so the publisher can fix it."
          : "The decision did not go through. Try again."
      );
    } finally {
      setPending(false);
    }
  }, [decision, note, refresh]);

  const toggleFeatured = React.useCallback(
    async (listing: ModerationListing) => {
      try {
        await featureListingAction(listing.id, !listing.is_featured);
        await refresh();
      } catch {
        setError("Could not change the featured flag.");
      }
    },
    [refresh]
  );

  if (queue.length === 0) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="Nothing waiting for review"
        description="Submitted listings appear here, oldest first. This page is only reachable by platform staff."
      />
    );
  }

  return (
    <div className="space-y-4">
      {error !== null && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {queue.map((listing) => (
        <Card key={listing.id} className="gap-3 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="font-medium">{listing.title}</h2>
                {listing.is_featured && (
                  <Star className="size-4 fill-current text-warning" aria-label="Featured" />
                )}
              </div>
              <p className="text-sm text-muted-foreground">{listing.summary}</p>
              {/* No submitted-at timestamp: `ListingResponse` does not
                  carry one, and inventing a date here would be worse
                  than omitting it. Queue order already encodes age —
                  the API returns oldest first. */}
              <p className="mt-1 text-xs text-muted-foreground">
                by {listing.publisher_name} · {listing.category_slug} · v
                {listing.latest_version}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {/* The public page is the thing being judged — reviewing a
                  listing from a summary alone is how bad ones get
                  through. */}
              <Button variant="ghost" size="sm" asChild>
                <Link href={`/docs/marketplace/publish-a-listing`} target="_blank">
                  <ExternalLink className="size-4" />
                  Criteria
                </Link>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void toggleFeatured(listing)}
              >
                <Star className="size-4" />
                {listing.is_featured ? "Unfeature" : "Feature"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setDecision({ listing, kind: "reject" });
                  setNote("");
                }}
              >
                <XCircle className="size-4" />
                Reject
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  setDecision({ listing, kind: "approve" });
                  setNote("");
                }}
              >
                <CheckCircle2 className="size-4" />
                Approve
              </Button>
            </div>
          </div>
        </Card>
      ))}

      <Dialog
        open={decision !== null}
        onOpenChange={(open) => {
          if (!open) setDecision(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {decision?.kind === "approve" ? "Publish" : "Reject"} “{decision?.listing.title}”?
            </DialogTitle>
            <DialogDescription>
              {decision?.kind === "approve"
                ? "It becomes installable by every workspace and appears in the public catalog and in search."
                : "It goes back to the publisher as a draft they can fix and resubmit."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="moderation-note">
              {decision?.kind === "approve" ? "Note (optional)" : "Reason"}
            </Label>
            <Textarea
              id="moderation-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={2000}
              rows={3}
              placeholder={
                decision?.kind === "approve"
                  ? "Anything worth recording for a later review."
                  : "What has to change before this can be published?"
              }
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDecision(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => void decide()}
              disabled={
                pending || (decision?.kind === "reject" && note.trim() === "")
              }
            >
              {decision?.kind === "approve" ? "Publish it" : "Send it back"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
