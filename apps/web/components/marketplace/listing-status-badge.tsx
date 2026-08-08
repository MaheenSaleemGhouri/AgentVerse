import * as React from "react";

import { StatusBadge } from "@/components/patterns/status-badge";

/**
 * A listing's lifecycle state, in the product's one status vocabulary.
 *
 * The mapping is deliberate rather than alphabetical: `pending` is
 * `info` because waiting on a human is not a problem, `rejected` is
 * `warning` rather than `danger` because it is fixable and resubmittable
 * — reserving `danger` for states the user cannot recover from keeps the
 * strongest tone meaningful.
 */
const TONES = {
  draft: "neutral",
  pending: "info",
  published: "success",
  rejected: "warning",
  unlisted: "neutral",
} as const;

const LABELS = {
  draft: "Draft",
  pending: "In review",
  published: "Published",
  rejected: "Changes requested",
  unlisted: "Unlisted",
} as const;

export function ListingStatusBadge({ status }: { status: string }): React.JSX.Element {
  const key = status in TONES ? (status as keyof typeof TONES) : "draft";
  return (
    <StatusBadge tone={TONES[key]} pulse={key === "pending"}>
      {LABELS[key]}
    </StatusBadge>
  );
}
