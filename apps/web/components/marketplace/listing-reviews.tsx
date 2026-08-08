"use client";

import { MessageSquareQuote, Star } from "lucide-react";
import * as React from "react";

import type { Review } from "@/lib/marketplace/types";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useReviews, useSubmitReview, useWithdrawReview } from "@/lib/queries/marketplace";

import { RatingStars } from "@/components/marketplace/rating-stars";
import { EmptyState } from "@/components/patterns/empty-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * Reviews, and the form to leave one.
 *
 * `canReview` is false for the publisher's own workspace. The API
 * refuses a self-review server-side regardless — this only stops the
 * form appearing where it could never succeed, which is the difference
 * between a control that is absent and one that fails when used.
 */
export function ListingReviews({
  workspaceId,
  slug,
  initialReviews,
  canReview,
}: {
  workspaceId: string;
  slug: string;
  initialReviews: Review[];
  canReview: boolean;
}): React.JSX.Element {
  const { data: reviews = [] } = useReviews(slug, initialReviews);

  return (
    <div className="flex flex-col gap-6">
      {canReview && <ReviewForm workspaceId={workspaceId} slug={slug} />}

      {reviews.length === 0 ? (
        <EmptyState
          icon={MessageSquareQuote}
          title="No reviews yet"
          description={
            canReview
              ? "Install it, use it, then tell other workspaces whether it did what it says."
              : "Nobody has reviewed this listing yet."
          }
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {reviews.map((review) => (
            <li key={review.id}>
              <Card className="gap-2 p-4">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">{review.reviewer_name}</span>
                  <RatingStars average={review.rating} size="sm" />
                  <time
                    dateTime={review.created_at}
                    className="ml-auto text-xs text-muted-foreground"
                  >
                    {formatRelativeTime(review.created_at)}
                  </time>
                </div>
                {review.body && (
                  <p className="text-sm whitespace-pre-wrap text-muted-foreground">
                    {review.body}
                  </p>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewForm({
  workspaceId,
  slug,
}: {
  workspaceId: string;
  slug: string;
}): React.JSX.Element {
  const [rating, setRating] = React.useState(0);
  const [body, setBody] = React.useState("");
  const submit = useSubmitReview(workspaceId, slug);
  const withdraw = useWithdrawReview(workspaceId, slug);

  return (
    <Card className="gap-4 p-5">
      <div className="space-y-2">
        <Label htmlFor="review-body">Your review</Label>
        {/* A radio group, not five buttons: exactly one rating can be
            chosen, arrow keys move between them, and the group has one
            tab stop. Buttons would give five tab stops and no grouping
            for a screen reader. */}
        <div role="radiogroup" aria-label="Rating out of five" className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={rating === value}
              aria-label={`${String(value)} ${value === 1 ? "star" : "stars"}`}
              onClick={() => setRating(value)}
              className="rounded p-1 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <Star
                aria-hidden="true"
                className={cn(
                  "size-5 transition-colors",
                  value <= rating
                    ? "fill-warning text-warning"
                    : "fill-transparent text-muted-foreground/50",
                )}
              />
            </button>
          ))}
          <span className="ml-2 text-sm text-muted-foreground">
            {rating === 0 ? "Pick a rating" : `${String(rating)} of 5`}
          </span>
        </div>
      </div>

      <Textarea
        id="review-body"
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder="What did it do well, and where did it fall short?"
        maxLength={4000}
        rows={3}
      />

      <div className="flex items-center gap-2">
        <Button
          disabled={rating === 0 || submit.isPending}
          onClick={() => submit.mutate({ rating, body })}
        >
          {submit.isPending ? "Publishing…" : "Publish review"}
        </Button>
        {/* Withdraw is offered unconditionally because the client cannot
            tell whether this workspace has an existing review — the
            reviews list carries workspace names, not ids. The API
            answers harmlessly if there is nothing to withdraw. */}
        <Button variant="ghost" disabled={withdraw.isPending} onClick={() => withdraw.mutate()}>
          Withdraw mine
        </Button>
      </div>
    </Card>
  );
}
