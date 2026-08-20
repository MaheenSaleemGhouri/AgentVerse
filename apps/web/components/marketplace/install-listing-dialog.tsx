"use client";

import { CreditCard, Download } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import type { Listing, ListingVersion } from "@/lib/marketplace/types";
import { formatPriceCents } from "@/lib/marketplace-format";
import { useInstallListing, useStartMarketplaceCheckout } from "@/lib/queries/marketplace";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const LATEST = "latest";

/**
 * Install a listing into this workspace.
 *
 * A dialog rather than a one-click button, because installing writes an
 * agent into the workspace and there are two decisions worth offering
 * first: what to call it, and which version. Both have sensible
 * defaults, so the fast path is still open-and-confirm.
 *
 * It is not a destructive-action confirmation — installing is reversible
 * by deleting the agent, and the API is idempotent per (workspace,
 * listing, version), so a double submit returns the same agent rather
 * than two.
 */
export function InstallListingDialog({
  workspaceId,
  listing,
  versions,
}: {
  workspaceId: string;
  listing: Listing;
  versions: ListingVersion[];
}): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [version, setVersion] = React.useState<string>(LATEST);
  const install = useInstallListing(workspaceId);
  const checkout = useStartMarketplaceCheckout(workspaceId);

  const installable = listing.status === "published" && versions.length > 0;
  const isPremium = listing.pricing !== "free";

  async function onInstall(): Promise<void> {
    const result = await install.mutateAsync({
      slug: listing.slug,
      versionNumber: version === LATEST ? null : Number(version),
      name: name.trim() === "" ? null : name.trim(),
    });
    setOpen(false);
    // Straight to the agent it became. The install is only useful once
    // you are looking at what you installed.
    router.push(`/dashboard/${workspaceId}/agents/${result.agent_id}`);
  }

  async function onCheckout(): Promise<void> {
    const session = await checkout.mutateAsync(listing.slug);
    // A full navigation, not a fetch: Stripe's hosted Checkout page must
    // be the top-level document, and the install itself happens later,
    // out-of-band, when the checkout.session.completed webhook lands —
    // there is nothing more for this dialog to do once the browser
    // leaves for Stripe.
    window.location.href = session.checkout_url;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={!installable}>
          {isPremium ? <CreditCard /> : <Download />}
          {!installable ? "Not available" : isPremium ? "Buy" : "Install"}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isPremium ? "Buy " : "Install "}“{listing.title}”
          </DialogTitle>
          <DialogDescription>
            {isPremium
              ? "You'll pay through Stripe Checkout, then this listing's latest version installs into your workspace as a new agent automatically."
              : "This copies the listing's configuration into your workspace as a new agent. It is yours to edit — later versions of the listing will not overwrite it."}
          </DialogDescription>
        </DialogHeader>

        {isPremium ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border bg-muted px-4 py-3">
              <span className="text-sm text-muted-foreground">One-time purchase</span>
              <span className="text-lg font-semibold">
                {formatPriceCents(listing.price_cents)}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Installs the current version (v{listing.latest_version}). You are only charged once
              — future versions install for free through the same &ldquo;Install&rdquo; flow once
              you own this listing.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="install-name">Agent name</Label>
              <Input
                id="install-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={listing.title}
                maxLength={120}
              />
              <p className="text-xs text-muted-foreground">
                Defaults to the listing&rsquo;s title. Change it if you are installing more than
                one variant.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="install-version">Version</Label>
              <Select value={version} onValueChange={setVersion}>
                <SelectTrigger id="install-version">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={LATEST}>Latest</SelectItem>
                  {versions.map((entry) => (
                    <SelectItem key={entry.version_number} value={String(entry.version_number)}>
                      v{entry.version_number}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          {isPremium ? (
            <Button onClick={() => void onCheckout()} disabled={checkout.isPending}>
              {checkout.isPending ? "Starting checkout…" : "Continue to payment"}
            </Button>
          ) : (
            <Button onClick={() => void onInstall()} disabled={install.isPending}>
              {install.isPending ? "Installing…" : "Install"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
