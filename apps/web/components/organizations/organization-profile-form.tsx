"use client";

import * as React from "react";

import type { OrganizationSettings } from "@/lib/api/organization-settings";
import { formatDateTime } from "@/lib/format";
import { useUpdateOrganizationSettings } from "@/lib/queries/organization-settings";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/** Empty-string on screen means "unset" — sent as `null`, never `""`. */
function toNullableString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** Hex colour, matching the API's `brand_color` pattern exactly. Client-side
 *  only so the user gets told before a round trip — the server re-validates
 *  regardless (Rule 6: no control is client-side only). */
const HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export function OrganizationProfileForm({
  organizationId,
  initialSettings,
  canManage,
}: {
  organizationId: string;
  initialSettings: OrganizationSettings;
  canManage: boolean;
}): React.JSX.Element {
  const update = useUpdateOrganizationSettings(organizationId);

  const [logoUrl, setLogoUrl] = React.useState(initialSettings.logo_url ?? "");
  const [brandColor, setBrandColor] = React.useState(initialSettings.brand_color ?? "");
  const [customDomain, setCustomDomain] = React.useState(initialSettings.custom_domain ?? "");
  const [websiteUrl, setWebsiteUrl] = React.useState(initialSettings.website_url ?? "");
  const [supportEmail, setSupportEmail] = React.useState(initialSettings.support_email ?? "");
  const [description, setDescription] = React.useState(initialSettings.description ?? "");

  const isDirty =
    logoUrl !== (initialSettings.logo_url ?? "") ||
    brandColor !== (initialSettings.brand_color ?? "") ||
    customDomain !== (initialSettings.custom_domain ?? "") ||
    websiteUrl !== (initialSettings.website_url ?? "") ||
    supportEmail !== (initialSettings.support_email ?? "") ||
    description !== (initialSettings.description ?? "");

  const brandColorError =
    brandColor.trim() !== "" && !HEX_COLOR.test(brandColor.trim())
      ? "Use a hex colour such as #4F46E5."
      : null;

  function onSave(): void {
    update.mutate({
      logo_url: toNullableString(logoUrl),
      brand_color: toNullableString(brandColor),
      custom_domain: toNullableString(customDomain),
      website_url: toNullableString(websiteUrl),
      support_email: toNullableString(supportEmail),
      description: toNullableString(description),
    });
  }

  return (
    <Card className="gap-4 p-6">
      <div>
        <h2 className="font-medium">Organization profile</h2>
        <p className="text-sm text-muted-foreground">
          How this organization presents itself. Each workspace keeps its own branding — this is
          the organization&apos;s identity, not an override.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="org-logo-url">Logo URL</Label>
          <Input
            id="org-logo-url"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            placeholder="https://example.com/logo.png"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="org-brand-color">Brand color</Label>
          <div className="flex items-center gap-2">
            <Input
              id="org-brand-color"
              value={brandColor}
              onChange={(e) => setBrandColor(e.target.value)}
              placeholder="#4F46E5"
              disabled={!canManage}
              aria-invalid={brandColorError !== null}
              aria-describedby={brandColorError ? "org-brand-color-error" : undefined}
            />
            {/* Swatch, not a colour picker: it previews the typed value and
                stays out of the tab order because the input above is the
                real control. */}
            <span
              aria-hidden="true"
              className="size-9 shrink-0 rounded-md border border-border"
              style={
                brandColorError === null && brandColor.trim() !== ""
                  ? { backgroundColor: brandColor.trim() }
                  : undefined
              }
            />
          </div>
          {brandColorError ? (
            <p id="org-brand-color-error" className="text-xs text-destructive">
              {brandColorError}
            </p>
          ) : null}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="org-custom-domain">Custom domain</Label>
          <Input
            id="org-custom-domain"
            value={customDomain}
            onChange={(e) => setCustomDomain(e.target.value)}
            placeholder="acme.com"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="org-website-url">Website</Label>
          <Input
            id="org-website-url"
            value={websiteUrl}
            onChange={(e) => setWebsiteUrl(e.target.value)}
            placeholder="https://acme.com"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="org-support-email">Support email</Label>
          <Input
            id="org-support-email"
            type="email"
            value={supportEmail}
            onChange={(e) => setSupportEmail(e.target.value)}
            placeholder="support@acme.com"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="org-description">Description</Label>
          <Textarea
            id="org-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this organization does."
            rows={3}
            maxLength={2000}
            disabled={!canManage}
          />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        A custom domain must resolve to exactly one organization — saving one already claimed
        elsewhere is rejected.
      </p>

      {canManage ? (
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">
            {initialSettings.updated_at
              ? `Last updated ${formatDateTime(initialSettings.updated_at)}`
              : "Never configured"}
          </span>
          <div className="flex items-center gap-3">
            {isDirty && <span className="text-xs text-warning">Unsaved changes</span>}
            <Button
              onClick={onSave}
              disabled={!isDirty || brandColorError !== null || update.isPending}
            >
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Only organization admins and owners can change the profile.
        </p>
      )}
    </Card>
  );
}
