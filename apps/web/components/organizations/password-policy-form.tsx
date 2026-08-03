"use client";

import * as React from "react";

import type { PasswordPolicy } from "@/lib/api/security";
import { useSetPasswordPolicy } from "@/lib/queries/security";

import { StatusBadge } from "@/components/patterns/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

const RULES = [
  { key: "require_uppercase", label: "Require an uppercase letter" },
  { key: "require_lowercase", label: "Require a lowercase letter" },
  { key: "require_number", label: "Require a number" },
  { key: "require_symbol", label: "Require a symbol" },
] as const;

type RuleKey = (typeof RULES)[number]["key"];

export function PasswordPolicyForm({
  organizationId,
  initialPolicy,
  canManage,
}: {
  organizationId: string;
  initialPolicy: PasswordPolicy;
  canManage: boolean;
}): React.JSX.Element {
  const save = useSetPasswordPolicy(organizationId);

  const [minLength, setMinLength] = React.useState(String(initialPolicy.min_length));
  const [rules, setRules] = React.useState<Record<RuleKey, boolean>>({
    require_uppercase: initialPolicy.require_uppercase,
    require_lowercase: initialPolicy.require_lowercase,
    require_number: initialPolicy.require_number,
    require_symbol: initialPolicy.require_symbol,
  });
  const [maxAgeDays, setMaxAgeDays] = React.useState(
    initialPolicy.max_age_days === null ? "" : String(initialPolicy.max_age_days)
  );

  const parsedMinLength = Number(minLength);
  // Mirrors the API's floor and the table's CHECK. Enforced server-side
  // regardless — this only avoids a round trip to be told the same thing.
  const minLengthError =
    !Number.isInteger(parsedMinLength) || parsedMinLength < 8 || parsedMinLength > 128
      ? "Must be a whole number between 8 and 128."
      : null;

  function onSave(): void {
    const trimmedAge = maxAgeDays.trim();
    save.mutate({
      min_length: parsedMinLength,
      ...rules,
      max_age_days: trimmedAge === "" ? null : Number(trimmedAge),
    });
  }

  return (
    <Card className="gap-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-medium">Password policy</h2>
          <p className="text-sm text-muted-foreground">
            Applies to everyone who signs in with a password in this organization.
          </p>
        </div>
        {/* "Default" and "configured" must be distinguishable — a
            default presented as a choice makes an unconfigured org look
            hardened when nobody has decided anything. */}
        <StatusBadge tone={initialPolicy.is_configured ? "success" : "neutral"}>
          {initialPolicy.is_configured ? "configured" : "platform default"}
        </StatusBadge>
      </div>

      <Separator />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="policy-min-length">Minimum length</Label>
          <Input
            id="policy-min-length"
            type="number"
            min={8}
            max={128}
            value={minLength}
            onChange={(e) => setMinLength(e.target.value)}
            disabled={!canManage}
            aria-invalid={minLengthError !== null}
            aria-describedby={minLengthError ? "policy-min-length-error" : undefined}
          />
          {minLengthError ? (
            <p id="policy-min-length-error" className="text-xs text-destructive">
              {minLengthError}
            </p>
          ) : null}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="policy-max-age">Expire passwords after (days)</Label>
          <Input
            id="policy-max-age"
            type="number"
            min={1}
            max={3650}
            value={maxAgeDays}
            onChange={(e) => setMaxAgeDays(e.target.value)}
            placeholder="Never"
            disabled={!canManage}
          />
        </div>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Character requirements</legend>
        {RULES.map((rule) => (
          <div key={rule.key} className="flex items-center gap-2">
            <Checkbox
              id={`policy-${rule.key}`}
              checked={rules[rule.key]}
              disabled={!canManage}
              onCheckedChange={(checked) =>
                setRules((current) => ({ ...current, [rule.key]: checked === true }))
              }
            />
            <Label htmlFor={`policy-${rule.key}`} className="text-sm font-normal">
              {rule.label}
            </Label>
          </div>
        ))}
      </fieldset>

      <p className="text-xs text-muted-foreground">
        Forced expiry is off by default — periodic rotation is no longer recommended practice
        (NIST SP 800-63B). Set it only if your own compliance regime requires it.
      </p>

      {canManage ? (
        <div className="flex justify-end">
          <Button onClick={onSave} disabled={minLengthError !== null || save.isPending}>
            {save.isPending ? "Saving…" : "Save policy"}
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Only organization admins and owners can change the password policy.
        </p>
      )}
    </Card>
  );
}
