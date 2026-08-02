"use client";

import { KeyRound, ShieldCheck, Trash2 } from "lucide-react";
import * as React from "react";

import type { SsoConfiguration } from "@/lib/api/sso";
import { formatRelativeTime } from "@/lib/format";
import {
  useDeleteSsoConfiguration,
  useSaveSsoConfiguration,
  useSsoConfigurations,
} from "@/lib/queries/sso";
import { SSO_PRESETS, type SsoPresetDefinition } from "@/lib/sso-presets";

import { EmptyState } from "@/components/patterns/empty-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

const PROTOCOL_LABEL: Record<string, string> = {
  oidc: "OpenID Connect",
  saml: "SAML 2.0",
};

export function SsoConfigPanel({
  organizationId,
  initialConfigurations,
  spEntityId,
  spAcsUrl,
}: {
  organizationId: string;
  initialConfigurations: SsoConfiguration[];
  /** Resolved server-side so the browser never has to guess the origin. */
  spEntityId: string;
  spAcsUrl: string;
}): React.JSX.Element {
  const { data: configurations } = useSsoConfigurations(organizationId, initialConfigurations);
  const save = useSaveSsoConfiguration(organizationId);
  const remove = useDeleteSsoConfiguration(organizationId);

  const [preset, setPreset] = React.useState<SsoPresetDefinition | null>(null);
  const [issuerUrl, setIssuerUrl] = React.useState("");
  const [clientId, setClientId] = React.useState("");
  const [clientSecret, setClientSecret] = React.useState("");
  const [ssoUrl, setSsoUrl] = React.useState("");
  const [idpCertificate, setIdpCertificate] = React.useState("");
  const [idpEntityId, setIdpEntityId] = React.useState("");
  const [enabled, setEnabled] = React.useState(false);

  function choosePreset(definition: SsoPresetDefinition): void {
    setPreset(definition);
    setIssuerUrl(definition.issuerUrlTemplate ?? "");
    setClientId("");
    setClientSecret("");
    setSsoUrl("");
    setIdpCertificate("");
    setIdpEntityId("");
    setEnabled(false);
  }

  function submit(): void {
    if (!preset) return;
    save.mutate(
      {
        protocol: preset.protocol,
        preset: preset.id,
        issuer_url: preset.protocol === "oidc" ? issuerUrl.trim() || null : null,
        client_id: preset.protocol === "oidc" ? clientId.trim() || null : null,
        // Omitted when blank, so re-saving never wipes a stored secret.
        ...(clientSecret.trim() ? { client_secret: clientSecret.trim() } : {}),
        protocol_config:
          preset.protocol === "saml"
            ? {
                idp_sso_url: ssoUrl.trim(),
                idp_certificate: idpCertificate.trim(),
                idp_entity_id: idpEntityId.trim(),
              }
            : {},
        enabled,
      },
      { onSuccess: () => setPreset(null) }
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-medium">Identity providers</h2>
          <p className="text-sm text-muted-foreground">
            One configuration per protocol. Presets only pre-fill the form — every provider
            uses the same generic OIDC or SAML flow underneath.
          </p>
        </div>
      </div>

      {(configurations ?? []).length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No identity provider configured"
          description="Members sign in with email, password, and any enabled social provider. Choose an IdP below to add SSO."
        />
      ) : (
        <div className="space-y-2">
          {(configurations ?? []).map((config) => (
            <Card key={config.id} className="flex-row items-center gap-4 p-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-medium">
                    {PROTOCOL_LABEL[config.protocol] ?? config.protocol}
                  </p>
                  <StatusBadge tone={config.enabled ? "success" : "neutral"}>
                    {config.enabled ? "Enabled" : "Disabled"}
                  </StatusBadge>
                  {config.has_client_secret && (
                    <StatusBadge tone="info">Secret stored</StatusBadge>
                  )}
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {config.issuer_url ??
                    config.protocol_config.idp_sso_url ??
                    "No issuer configured"}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Updated {formatRelativeTime(config.updated_at)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${config.protocol} configuration`}
                onClick={() => remove.mutate(config.id)}
                disabled={remove.isPending}
              >
                <Trash2 />
              </Button>
            </Card>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-sm font-medium">Add an identity provider</h3>
        <div className="grid gap-2 sm:grid-cols-2">
          {SSO_PRESETS.map((definition) => (
            <button
              key={`${definition.id}-${definition.protocol}-${definition.label}`}
              type="button"
              onClick={() => choosePreset(definition)}
              className="rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/40 focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
            >
              <p className="text-sm font-medium">{definition.label}</p>
              <p className="text-xs text-muted-foreground">
                {PROTOCOL_LABEL[definition.protocol]}
              </p>
            </button>
          ))}
        </div>
      </div>

      <Dialog open={preset !== null} onOpenChange={(next) => !next && setPreset(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Configure {preset?.label}</DialogTitle>
            <DialogDescription>{preset?.hint}</DialogDescription>
          </DialogHeader>

          {preset?.protocol === "oidc" ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="sso-issuer">Issuer URL</Label>
                <Input
                  id="sso-issuer"
                  value={issuerUrl}
                  onChange={(event) => setIssuerUrl(event.target.value)}
                  placeholder="https://idp.example.com"
                  className="font-mono text-xs"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sso-client-id">Client ID</Label>
                <Input
                  id="sso-client-id"
                  value={clientId}
                  onChange={(event) => setClientId(event.target.value)}
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="sso-client-secret">Client secret</Label>
                <Input
                  id="sso-client-secret"
                  type="password"
                  value={clientSecret}
                  onChange={(event) => setClientSecret(event.target.value)}
                  placeholder="Leave blank to keep the stored secret"
                />
                <p className="text-xs text-muted-foreground">
                  Encrypted at rest and never shown again after saving.
                </p>
              </div>
            </>
          ) : (
            <>
              {/* The admin must configure these two on the IdP side
                  first — a SAML app that does not know the ACS URL and
                  Audience cannot send a valid assertion at all. */}
              <div className="space-y-2 rounded-lg border border-border bg-muted/50 p-3">
                <p className="text-xs font-medium">Give these to your IdP</p>
                <div className="space-y-1">
                  <p className="text-[11px] text-muted-foreground">ACS / Reply URL</p>
                  <code className="block font-mono text-[11px] break-all">
                    {spAcsUrl}
                  </code>
                </div>
                <div className="space-y-1">
                  <p className="text-[11px] text-muted-foreground">Entity ID / Audience</p>
                  <code className="block font-mono text-[11px] break-all">{spEntityId}</code>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="saml-sso-url">IdP SSO URL</Label>
                <Input
                  id="saml-sso-url"
                  value={ssoUrl}
                  onChange={(event) => setSsoUrl(event.target.value)}
                  placeholder="https://idp.example.com/sso/saml"
                  className="font-mono text-xs"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="saml-entity-id">IdP Entity ID</Label>
                <Input
                  id="saml-entity-id"
                  value={idpEntityId}
                  onChange={(event) => setIdpEntityId(event.target.value)}
                  placeholder="http://www.okta.com/exk123"
                  className="font-mono text-xs"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="saml-cert">IdP signing certificate</Label>
                <textarea
                  id="saml-cert"
                  value={idpCertificate}
                  onChange={(event) => setIdpCertificate(event.target.value)}
                  rows={4}
                  placeholder="-----BEGIN CERTIFICATE-----"
                  className="w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-[11px] shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                />
                <p className="text-xs text-muted-foreground">
                  Every assertion is verified against this. Without it, sign-in is refused.
                </p>
              </div>
            </>
          )}

          <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
            <div>
              <Label htmlFor="sso-enabled">Enable for this organization</Label>
              <p className="text-xs text-muted-foreground">
                Save it disabled first if you want to check the values before it goes live.
              </p>
            </div>
            <Switch id="sso-enabled" checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <Alert tone="info">
            <KeyRound />
            <AlertTitle>Takes effect on the next restart</AlertTitle>
            <AlertDescription>
              The secret is encrypted immediately, but providers are registered when the
              application starts — an enabled configuration appears on the login page after
              the next deploy or restart.
            </AlertDescription>
          </Alert>

          <DialogFooter>
            <Button variant="outline" onClick={() => setPreset(null)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save configuration"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
