"use client";

import { Check, Share2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useShareListing } from "@/lib/queries/marketplace";

import { Button } from "@/components/ui/button";

/**
 * Copies a referral-attributed link to this listing and records that a
 * share happened (Phase 11's growth loop). The link carries the
 * *sharer's* own referral code — reused as-is from `billing_service`'s
 * existing workspace-level code, not a new per-listing token — so
 * whoever signs up through it attributes back to whoever shared it, not
 * to the listing's publisher.
 */
export function ShareListingButton({
  workspaceId,
  slug,
  referralCode,
}: {
  workspaceId: string;
  slug: string;
  referralCode: string;
}): React.JSX.Element {
  const share = useShareListing(workspaceId);
  const [copied, setCopied] = React.useState(false);

  const handleShare = async (): Promise<void> => {
    const link = `${window.location.origin}/marketplace/${slug}?ref=${referralCode}`;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy the link — copy it manually from your browser's address bar.");
      return;
    }
    share.mutate(slug);
  };

  return (
    <Button variant="outline" onClick={() => void handleShare()}>
      {copied ? (
        <>
          <Check className="size-4" aria-hidden="true" />
          Link copied
        </>
      ) : (
        <>
          <Share2 className="size-4" aria-hidden="true" />
          Share
        </>
      )}
    </Button>
  );
}
