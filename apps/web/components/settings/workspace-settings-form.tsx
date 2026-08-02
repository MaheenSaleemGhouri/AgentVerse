"use client";

import * as React from "react";

import type { WorkspaceSettings } from "@/lib/api/workspace-settings";
import { formatDateTime } from "@/lib/format";
import { useUpdateWorkspaceSettings } from "@/lib/queries/workspace-settings";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Empty-string on screen means "unset" — sent as `null`, never `""`. */
function toNullableString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function toNullableInt(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

export function WorkspaceSettingsForm({
  workspaceId,
  initialSettings,
  canManage,
}: {
  workspaceId: string;
  initialSettings: WorkspaceSettings;
  canManage: boolean;
}): React.JSX.Element {
  const update = useUpdateWorkspaceSettings(workspaceId);

  const [logoUrl, setLogoUrl] = React.useState(initialSettings.logo_url ?? "");
  const [brandColor, setBrandColor] = React.useState(initialSettings.brand_color ?? "");
  const [customDomain, setCustomDomain] = React.useState(initialSettings.custom_domain ?? "");
  const [retentionDays, setRetentionDays] = React.useState(
    initialSettings.retention_days === null ? "" : String(initialSettings.retention_days)
  );
  const [storageLimitMb, setStorageLimitMb] = React.useState(
    initialSettings.storage_limit_mb === null ? "" : String(initialSettings.storage_limit_mb)
  );

  const isDirty =
    logoUrl !== (initialSettings.logo_url ?? "") ||
    brandColor !== (initialSettings.brand_color ?? "") ||
    customDomain !== (initialSettings.custom_domain ?? "") ||
    retentionDays !== (initialSettings.retention_days === null ? "" : String(initialSettings.retention_days)) ||
    storageLimitMb !== (initialSettings.storage_limit_mb === null ? "" : String(initialSettings.storage_limit_mb));

  function onSave(): void {
    update.mutate({
      logo_url: toNullableString(logoUrl),
      brand_color: toNullableString(brandColor),
      custom_domain: toNullableString(customDomain),
      retention_days: toNullableInt(retentionDays),
      storage_limit_mb: toNullableInt(storageLimitMb),
    });
  }

  return (
    <Card className="gap-4 p-6">
      <div>
        <h2 className="font-medium">Branding &amp; policy</h2>
        <p className="text-sm text-muted-foreground">
          Workspace-wide, seen by every member — distinct from your own light/dark theme
          preference under Appearance.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="ws-logo-url">Logo URL</Label>
          <Input
            id="ws-logo-url"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            placeholder="https://example.com/logo.png"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="ws-brand-color">Brand color</Label>
          <Input
            id="ws-brand-color"
            value={brandColor}
            onChange={(e) => setBrandColor(e.target.value)}
            placeholder="#4F46E5"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="ws-custom-domain">Custom domain</Label>
          <Input
            id="ws-custom-domain"
            value={customDomain}
            onChange={(e) => setCustomDomain(e.target.value)}
            placeholder="app.acme.com"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="ws-retention-days">Retention (days)</Label>
          <Input
            id="ws-retention-days"
            type="number"
            min={1}
            max={3650}
            value={retentionDays}
            onChange={(e) => setRetentionDays(e.target.value)}
            placeholder="Unset — kept indefinitely"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="ws-storage-limit">Storage limit (MB)</Label>
          <Input
            id="ws-storage-limit"
            type="number"
            min={1}
            value={storageLimitMb}
            onChange={(e) => setStorageLimitMb(e.target.value)}
            placeholder="Unset — no limit"
            disabled={!canManage}
          />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Both are enforced. Run history older than the retention window is deleted hourly and the
        deletion is recorded in the audit log; uploads that would exceed the storage limit are
        refused. Leave either unset to keep it unrestricted.
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
            <Button onClick={onSave} disabled={!isDirty || update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Only workspace admins and owners can change these settings.
        </p>
      )}
    </Card>
  );
}
