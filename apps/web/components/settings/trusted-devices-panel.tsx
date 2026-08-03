"use client";

import { Laptop, Trash2 } from "lucide-react";
import * as React from "react";

import type { TrustedDevice } from "@/lib/api/security";
import { formatDateTime } from "@/lib/format";
import { useMyDevices, useRevokeDevice } from "@/lib/queries/security";

import { EmptyState } from "@/components/patterns/empty-state";
import { StatusBadge } from "@/components/patterns/status-badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/**
 * Devices this account has confirmed. Signing in from anything else is
 * recorded as a new-device event.
 *
 * Distinct from the Sessions panel above it: a session is one live
 * sign-in and revoking it signs you out; a trusted device is a standing
 * "this machine is mine" and revoking it only means the next sign-in
 * from it gets reported.
 */
export function TrustedDevicesPanel({
  initialDevices,
}: {
  initialDevices: TrustedDevice[];
}): React.JSX.Element {
  const { data: devices } = useMyDevices(initialDevices);
  const revoke = useRevokeDevice();
  const [pendingRevoke, setPendingRevoke] = React.useState<TrustedDevice | null>(null);

  const active = (devices ?? []).filter((device) => device.revoked_at === null);

  return (
    <Card className="gap-4 p-6">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Laptop className="size-4.5" aria-hidden="true" />
        </span>
        <div>
          <h2 className="font-medium">Trusted devices</h2>
          <p className="text-sm text-muted-foreground">
            Signing in from anything not listed here is recorded as a new-device event. Revoking a
            device does not sign it out — it stops being recognised.
          </p>
        </div>
      </div>
      <Separator />

      {active.length === 0 ? (
        <EmptyState
          icon={Laptop}
          title="No trusted devices"
          description="Every sign-in is currently reported as coming from a new device."
        />
      ) : (
        <ul className="space-y-3">
          {active.map((device) => (
            <li key={device.id} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm">{device.device_name ?? "Unnamed device"}</span>
                  <StatusBadge tone="success">trusted</StatusBadge>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  Last seen {formatDateTime(device.last_seen_at)}
                  {device.ip_address ? ` · ${device.ip_address}` : ""}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPendingRevoke(device)}
                disabled={revoke.isPending}
              >
                <Trash2 aria-hidden="true" />
                <span className="sr-only">
                  Revoke {device.device_name ?? "unnamed device"}
                </span>
              </Button>
            </li>
          ))}
        </ul>
      )}

      <AlertDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Revoke {pendingRevoke?.device_name ?? "this device"}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              It stays signed in — revoking only means the next sign-in from it is reported as
              new. To sign it out, revoke its session instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                if (pendingRevoke) revoke.mutate(pendingRevoke.id);
                setPendingRevoke(null);
              }}
            >
              Revoke device
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
