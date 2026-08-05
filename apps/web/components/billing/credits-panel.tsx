"use client";

import { Gift, Loader2, Wallet } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CreditBalance } from "@/lib/api/billing";
import { formatCents, formatDate, formatRelativeTime } from "@/lib/format";

/**
 * Balance, the ledger behind it, and coupon redemption.
 *
 * The ledger is shown alongside the balance rather than hidden behind a
 * link because "why is this $40 and not $50" is the first question
 * anyone asks about credit, and the answer is one scroll away rather
 * than a support ticket.
 *
 * `direction` comes from the server rather than being inferred from the
 * amount's sign — the API sends positive magnitudes, and re-deriving
 * direction in the client is exactly the place a statement starts
 * showing debits as credits.
 */
const REASON_LABELS: Record<string, string> = {
  referral_reward: "Referral reward",
  coupon_redemption: "Coupon",
  promotional_grant: "Promotional credit",
  refund_to_account: "Refund to account",
  support_adjustment: "Support adjustment",
  invoice_applied: "Applied to invoice",
  expired: "Expired",
};

export function CreditsPanel({
  credits,
  onRedeem,
  isRedeeming,
  canRedeem,
}: {
  credits: CreditBalance;
  onRedeem: (code: string) => void;
  isRedeeming: boolean;
  canRedeem: boolean;
}): React.JSX.Element {
  const [code, setCode] = React.useState("");

  function submit(event: React.FormEvent): void {
    event.preventDefault();
    const trimmed = code.trim();
    if (!trimmed) return;
    onRedeem(trimmed);
    setCode("");
  }

  return (
    <Card className="gap-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 font-medium">
            <Wallet className="size-4 text-muted-foreground" aria-hidden="true" />
            Account credit
          </h2>
          <p className="text-sm text-muted-foreground">
            Applied automatically to your next invoice.
          </p>
        </div>
        <p className="text-3xl font-semibold tracking-tight tabular-nums">
          {formatCents(credits.balance_cents, credits.currency)}
        </p>
      </div>

      {canRedeem && (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2 border-t border-border pt-4">
          <div className="min-w-50 flex-1 space-y-1.5">
            <Label htmlFor="coupon-code">Have a code?</Label>
            <Input
              id="coupon-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="WELCOME20"
              autoComplete="off"
              // Uppercased visually only; the server normalises for real,
              // so a pasted lowercase code still works.
              className="uppercase"
              maxLength={64}
            />
          </div>
          <Button type="submit" variant="outline" disabled={isRedeeming || !code.trim()}>
            {isRedeeming ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Gift className="size-4" aria-hidden="true" />
            )}
            Redeem
          </Button>
        </form>
      )}

      <div className="space-y-2 border-t border-border pt-4">
        <h3 className="text-sm font-medium text-muted-foreground">History</h3>
        {credits.transactions.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            No credit activity yet. Referral rewards and coupons appear here.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {credits.transactions.map((transaction) => (
              <li key={transaction.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0 space-y-0.5">
                  <p className="truncate text-sm">
                    {transaction.description ||
                      REASON_LABELS[transaction.reason] ||
                      transaction.reason}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatRelativeTime(transaction.created_at)}
                    {transaction.expires_at &&
                      ` · expires ${formatDate(transaction.expires_at)}`}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p
                    className={
                      transaction.direction === "credit"
                        ? "text-sm font-medium tabular-nums text-success"
                        : "text-sm font-medium tabular-nums text-muted-foreground"
                    }
                  >
                    {transaction.direction === "credit" ? "+" : "−"}
                    {formatCents(transaction.amount_cents, credits.currency)}
                  </p>
                  <p className="text-xs tabular-nums text-muted-foreground">
                    {formatCents(transaction.balance_after_cents, credits.currency)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

/**
 * The referral programme's own panel.
 *
 * Pending referrals are shown alongside rewarded ones deliberately: the
 * ratio between them is the loop efficiency the programme is judged by,
 * and a panel showing only successes would let a loop that never
 * converts look like it works.
 */
export function ReferralPanel({
  summary,
  currency,
}: {
  summary: {
    code: string;
    pending: number;
    qualified: number;
    rewarded: number;
    total_earned_cents: number;
  };
  currency: string;
}): React.JSX.Element {
  const [copied, setCopied] = React.useState(false);
  const link = `https://agentverse.dev/signup?ref=${summary.code}`;

  async function copy(): Promise<void> {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Card className="gap-5 p-6">
      <div className="space-y-1">
        <h2 className="font-medium">Refer a team</h2>
        <p className="text-sm text-muted-foreground">
          You both get credit once they make their first payment — not at
          signup, so the reward tracks real usage.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-50 flex-1 space-y-1.5">
          <Label htmlFor="referral-link">Your referral link</Label>
          <Input id="referral-link" readOnly value={link} className="font-mono text-xs" />
        </div>
        <Button variant="outline" onClick={copy}>
          {copied ? "Copied" : "Copy link"}
        </Button>
      </div>

      <dl className="grid grid-cols-3 gap-4 border-t border-border pt-4">
        <div className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">Pending</dt>
          <dd className="text-lg font-semibold tabular-nums">{summary.pending}</dd>
        </div>
        <div className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">Rewarded</dt>
          <dd className="text-lg font-semibold tabular-nums">{summary.rewarded}</dd>
        </div>
        <div className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">Earned</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {formatCents(summary.total_earned_cents, currency)}
          </dd>
        </div>
      </dl>

      {summary.qualified > 0 && (
        <Badge variant="secondary" className="w-fit">
          {summary.qualified} qualified, reward pending
        </Badge>
      )}
    </Card>
  );
}
