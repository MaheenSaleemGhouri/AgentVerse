"use client";

import { KeyRound, ShieldCheck } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { authClient } from "@/lib/auth-client";

import { CopyButton } from "@/components/patterns/copy-button";
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

/**
 * TOTP enrolment against Better Auth's `twoFactor()` plugin
 * (Increment 7.2). Enabling requires the current password (Better Auth's
 * own requirement) and is only complete once a generated code verifies —
 * enrolling without that step would leave an account "protected" by an
 * authenticator the user never actually scanned.
 */
export function TwoFactorPanel({ enabled }: { enabled: boolean }): React.JSX.Element {
  const [isEnabled, setIsEnabled] = React.useState(enabled);
  const [enrollOpen, setEnrollOpen] = React.useState(false);
  const [disableOpen, setDisableOpen] = React.useState(false);
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [totpUri, setTotpUri] = React.useState<string | null>(null);
  const [backupCodes, setBackupCodes] = React.useState<string[]>([]);
  const [pending, setPending] = React.useState(false);

  function resetDialogState(): void {
    setPassword("");
    setCode("");
    setTotpUri(null);
    setBackupCodes([]);
  }

  async function startEnrolment(): Promise<void> {
    setPending(true);
    const { data, error } = await authClient.twoFactor.enable({ password });
    setPending(false);
    if (error || !data) {
      toast.error(error?.message ?? "Could not start setup — check your password.");
      return;
    }
    setTotpUri(data.totpURI);
    setBackupCodes(data.backupCodes);
  }

  async function confirmEnrolment(): Promise<void> {
    setPending(true);
    const { error } = await authClient.twoFactor.verifyTotp({ code });
    setPending(false);
    if (error) {
      toast.error(error.message ?? "That code did not match. Try the next one.");
      return;
    }
    setIsEnabled(true);
    setEnrollOpen(false);
    resetDialogState();
    toast.success("Two-factor authentication is on.");
  }

  async function disable(): Promise<void> {
    setPending(true);
    const { error } = await authClient.twoFactor.disable({ password });
    setPending(false);
    if (error) {
      toast.error(error.message ?? "Could not turn it off — check your password.");
      return;
    }
    setIsEnabled(false);
    setDisableOpen(false);
    resetDialogState();
    toast.success("Two-factor authentication is off.");
  }

  return (
    <Card className="gap-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 font-medium">
            Two-factor authentication
            <StatusBadge tone={isEnabled ? "success" : "neutral"}>
              {isEnabled ? "On" : "Off"}
            </StatusBadge>
          </h2>
          <p className="text-sm text-muted-foreground">
            Require a code from your authenticator app in addition to your password.
          </p>
        </div>
        {isEnabled ? (
          <Button variant="outline" onClick={() => setDisableOpen(true)}>
            Turn off
          </Button>
        ) : (
          <Button onClick={() => setEnrollOpen(true)}>
            <ShieldCheck />
            Turn on
          </Button>
        )}
      </div>

      <Dialog
        open={enrollOpen}
        onOpenChange={(next) => {
          setEnrollOpen(next);
          if (!next) resetDialogState();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Set up two-factor authentication</DialogTitle>
            <DialogDescription>
              {totpUri
                ? "Add this to your authenticator app, then enter a code from it to finish."
                : "Confirm your password to begin."}
            </DialogDescription>
          </DialogHeader>

          {!totpUri ? (
            <div className="space-y-2">
              <Label htmlFor="tf-password">Current password</Label>
              <Input
                id="tf-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void startEnrolment()}
                autoFocus
              />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="tf-uri">Setup key</Label>
                <div className="flex items-center gap-2 rounded-lg border border-border bg-muted p-3">
                  <code
                    id="tf-uri"
                    className="min-w-0 flex-1 font-mono text-xs break-all"
                  >
                    {totpUri}
                  </code>
                  <CopyButton value={totpUri} label="Copy setup key" />
                </div>
              </div>

              <Alert tone="warning">
                <KeyRound />
                <AlertTitle>Save your backup codes</AlertTitle>
                <AlertDescription>
                  Each works once if you lose your authenticator. They are shown only now.
                </AlertDescription>
              </Alert>
              <div className="grid grid-cols-2 gap-1.5 rounded-lg border border-border bg-muted p-3">
                {backupCodes.map((backupCode) => (
                  <code key={backupCode} className="font-mono text-xs">
                    {backupCode}
                  </code>
                ))}
              </div>

              <div className="space-y-2">
                <Label htmlFor="tf-code">Code from your app</Label>
                <Input
                  id="tf-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && void confirmEnrolment()}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setEnrollOpen(false)}>
              Cancel
            </Button>
            {!totpUri ? (
              <Button onClick={() => void startEnrolment()} disabled={!password || pending}>
                {pending ? "Checking…" : "Continue"}
              </Button>
            ) : (
              <Button onClick={() => void confirmEnrolment()} disabled={!code || pending}>
                {pending ? "Verifying…" : "Finish setup"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={disableOpen}
        onOpenChange={(next) => {
          setDisableOpen(next);
          if (!next) resetDialogState();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Turn off two-factor authentication?</DialogTitle>
            <DialogDescription>
              Your account will be protected by your password alone.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="tf-disable-password">Current password</Label>
            <Input
              id="tf-disable-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void disable()}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisableOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void disable()} disabled={!password || pending}>
              {pending ? "Turning off…" : "Turn off"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
