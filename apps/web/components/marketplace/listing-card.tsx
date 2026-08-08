import { BadgeCheck, Download, Package } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { Listing } from "@/lib/marketplace/types";
import { formatNumber } from "@/lib/format";
import { formatPriceCents } from "@/lib/marketplace-format";

import { RatingStars } from "@/components/marketplace/rating-stars";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

/**
 * A catalog tile.
 *
 * Composed from Card + Badge, and using the same whole-card overlay-link
 * pattern as `AgentCard` so exactly one link lands in the accessibility
 * tree rather than a card full of nested interactive elements. Install
 * happens on the detail page, not here — installing writes an agent into
 * the workspace, and that deserves a page where the version, the
 * publisher and the reviews are visible first.
 */
export function ListingCard({
  workspaceId,
  listing,
}: {
  workspaceId: string;
  listing: Listing;
}): React.JSX.Element {
  return (
    <Card className="group relative gap-0 p-5 transition-colors hover:border-primary/40">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
        >
          <Package className="size-4.5" />
        </span>

        <div className="min-w-0 flex-1">
          <Link
            href={`/dashboard/${workspaceId}/marketplace/${listing.slug}`}
            className="font-medium after:absolute after:inset-0 after:content-[''] hover:underline"
          >
            {listing.title}
          </Link>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
            {listing.is_official ? (
              <>
                <BadgeCheck className="size-3.5 text-primary" aria-hidden="true" />
                <span>AgentVerse official</span>
              </>
            ) : (
              <span>by {listing.publisher_name}</span>
            )}
          </p>
        </div>

        {/* Price, not status — a plain Badge, so the semantic status
            tones stay reserved for the lifecycle vocabulary. */}
        <Badge variant="secondary" className="shrink-0">
          {listing.pricing === "free" ? "Free" : formatPriceCents(listing.price_cents)}
        </Badge>
      </div>

      <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{listing.summary}</p>

      <div className="mt-4 flex items-center gap-3">
        <RatingStars average={listing.average_rating} count={listing.rating_count} size="sm" />
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
          <Download className="size-3.5" aria-hidden="true" />
          {formatNumber(listing.install_count)}
        </span>
      </div>
    </Card>
  );
}
