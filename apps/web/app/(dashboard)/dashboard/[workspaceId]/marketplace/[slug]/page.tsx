import { BadgeCheck, Download, Package } from "lucide-react";
import { notFound } from "next/navigation";
import * as React from "react";

import { getReferrals } from "@/lib/api/billing";
import { ApiError } from "@/lib/api/client";
import {
  getListing,
  listMyListings,
  listReviews,
  listVersions,
} from "@/lib/api/marketplace";
import { formatNumber, formatRelativeTime } from "@/lib/format";
import { formatPriceCents } from "@/lib/marketplace-format";

import { InstallListingDialog } from "@/components/marketplace/install-listing-dialog";
import { ListingReviews } from "@/components/marketplace/listing-reviews";
import { ListingStatusBadge } from "@/components/marketplace/listing-status-badge";
import { RatingStars } from "@/components/marketplace/rating-stars";
import { ShareListingButton } from "@/components/marketplace/share-listing-button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EmptyState } from "@/components/patterns/empty-state";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface PageProps {
  params: Promise<{ workspaceId: string; slug: string }>;
  searchParams: Promise<{ checkout?: string }>;
}

export default async function ListingDetailPage({
  params,
  searchParams,
}: PageProps): Promise<React.JSX.Element> {
  const { workspaceId, slug } = await params;
  const { checkout } = await searchParams;

  const listing = await getListing(slug).catch((error: unknown) => {
    // A listing this workspace may not see answers 404, not 403, so an
    // unpublished slug cannot be probed for existence. Rendering the
    // shared not-found page keeps that indistinguishable.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });

  const [versions, reviews, myListings, referrals] = await Promise.all([
    listVersions(slug),
    listReviews(slug),
    // The only way to know whether this workspace publishes this
    // listing: the public response carries `publisher_name`, not an id,
    // deliberately — a workspace id has no business on a public page.
    listMyListings(workspaceId),
    getReferrals(workspaceId),
  ]);

  const isMine = myListings.some((mine) => mine.slug === slug);

  return (
    <div className="flex flex-col gap-6">
      {checkout === "success" && (
        // The install itself lands out-of-band, when Stripe's webhook
        // confirms the charge — usually seconds, but never instant, so
        // this states "pending" honestly rather than implying the agent
        // is already there. A fresh page load once it lands (or a
        // moment later) shows the new install/install count normally.
        <Alert tone="success">
          <AlertTitle>Payment received</AlertTitle>
          <AlertDescription>
            Installing this listing into your workspace now — it lands within a few seconds.
            Check{" "}
            <a
              href={`/dashboard/${workspaceId}/agents`}
              className="font-medium underline underline-offset-2"
            >
              your agents
            </a>{" "}
            shortly if it isn&apos;t there yet.
          </AlertDescription>
        </Alert>
      )}
      {checkout === "cancelled" && (
        <Alert tone="info">
          <AlertTitle>Checkout cancelled</AlertTitle>
          <AlertDescription>No charge was made. You can buy this listing anytime.</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <span
          aria-hidden="true"
          className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground"
        >
          <Package className="size-6" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{listing.title}</h1>
            {listing.is_official && (
              <Badge variant="secondary" className="gap-1">
                <BadgeCheck className="size-3.5 text-primary" aria-hidden="true" />
                Official
              </Badge>
            )}
            {isMine && <ListingStatusBadge status={listing.status} />}
          </div>

          <p className="mt-1 text-sm text-muted-foreground">
            {listing.is_official ? "By AgentVerse" : `By ${listing.publisher_name}`}
          </p>
          <p className="mt-3 max-w-2xl text-muted-foreground">{listing.summary}</p>

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <RatingStars average={listing.average_rating} count={listing.rating_count} />
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Download className="size-4" aria-hidden="true" />
              {formatNumber(listing.install_count)} installs
            </span>
            <Badge variant="secondary">
              {listing.pricing === "free" ? "Free" : formatPriceCents(listing.price_cents)}
            </Badge>
          </div>
        </div>

        <div className="flex shrink-0 gap-2">
          <ShareListingButton
            workspaceId={workspaceId}
            slug={slug}
            referralCode={referrals.code}
          />
          <InstallListingDialog
            workspaceId={workspaceId}
            listing={listing}
            versions={versions}
          />
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="versions">Versions ({versions.length})</TabsTrigger>
          <TabsTrigger value="reviews">Reviews ({listing.rating_count})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-5">
          <Card className="p-6">
            {listing.description ? (
              <p className="max-w-3xl text-sm whitespace-pre-wrap text-muted-foreground">
                {listing.description}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                This listing has no long description.
              </p>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="versions" className="pt-5">
          {versions.length === 0 ? (
            <EmptyState
              icon={Package}
              title="No versions published"
              description="A listing needs at least one published version before it can be installed."
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {versions.map((version) => (
                <li key={version.version_number}>
                  <Card className="gap-1.5 p-4">
                    <div className="flex items-center gap-3">
                      <span className="font-medium">v{version.version_number}</span>
                      <time
                        dateTime={version.created_at}
                        className="ml-auto text-xs text-muted-foreground"
                      >
                        {formatRelativeTime(version.created_at)}
                      </time>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {version.changelog || "No changelog for this version."}
                    </p>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="reviews" className="pt-5">
          <ListingReviews
            workspaceId={workspaceId}
            slug={slug}
            initialReviews={reviews}
            canReview={!isMine}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export async function generateMetadata({ params }: PageProps): Promise<{ title: string }> {
  const { slug } = await params;
  const listing = await getListing(slug).catch(() => null);
  return { title: listing ? `${listing.title} · Marketplace` : "Marketplace · AgentVerse" };
}
