"use client";

import { CreditCard, Download, ExternalLink } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { DraftInvoice, Invoice, PaymentMethod } from "@/lib/api/billing";
import { formatCents, formatDate } from "@/lib/format";

/**
 * Invoices and payment methods, both read live from the payment
 * provider.
 *
 * `invoices === null` and `paymentMethods === null` mean the environment
 * has no payment provider configured — a first-class state, not a
 * failure. Local development, CI and preview environments legitimately
 * run that way, and the honest message is "not configured here", not a
 * generic error and certainly not an empty list that reads as "you have
 * no invoices".
 *
 * Invoice links go straight to the provider's hosted document rather
 * than being proxied: they are short-lived and signed, and re-serving
 * financial documents through this app would put them through
 * infrastructure with no reason to hold them.
 */
const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  paid: "default",
  open: "secondary",
  draft: "outline",
  uncollectible: "destructive",
  void: "outline",
};

export function ProviderUnavailableNotice(): React.JSX.Element {
  return (
    <Card className="gap-2 p-6">
      <h2 className="font-medium">Payments are not configured here</h2>
      <p className="text-sm text-muted-foreground">
        This environment runs without payment-provider credentials, so
        invoices and saved payment methods are unavailable. Everything else on
        this page — your plan, usage against quota and credit balance — is real.
      </p>
    </Card>
  );
}

export function InvoicesPanel({
  invoices,
  preview,
}: {
  invoices: Invoice[] | null;
  preview: DraftInvoice | null;
}): React.JSX.Element {
  return (
    <div className="space-y-6">
      {preview && preview.lines.length > 0 && (
        <Card className="gap-4 p-6">
          <div className="space-y-1">
            <h2 className="font-medium">This period so far</h2>
            <p className="text-sm text-muted-foreground">
              A forecast of {formatDate(preview.period_start)} –{" "}
              {formatDate(preview.period_end)}, updated as you use the platform.
              Nothing is charged until the period closes.
            </p>
          </div>
          <table className="w-full text-sm">
            <caption className="sr-only">Estimated charges for the current billing period</caption>
            <thead className="sr-only">
              <tr>
                <th scope="col">Line item</th>
                <th scope="col">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {preview.lines.map((line, index) => (
                <tr key={`${line.kind}-${line.dimension ?? index}`}>
                  <th scope="row" className="py-2.5 pr-4 text-left font-normal">
                    {line.description}
                  </th>
                  <td className="py-2.5 text-right tabular-nums">
                    {formatCents(line.amount_cents, preview.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-border">
                <th scope="row" className="pt-3 pr-4 text-left font-medium">
                  Estimated total
                </th>
                <td className="pt-3 text-right font-semibold tabular-nums">
                  {formatCents(preview.subtotal_cents, preview.currency)}
                </td>
              </tr>
            </tfoot>
          </table>
        </Card>
      )}

      {invoices === null ? (
        <ProviderUnavailableNotice />
      ) : (
        <Card className="gap-4 p-6">
          <h2 className="font-medium">Invoice history</h2>
          {invoices.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              No invoices yet. Your first one appears after your first billing
              period closes.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-125 text-sm">
                <caption className="sr-only">Past invoices for this workspace</caption>
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th scope="col" className="py-2.5 pr-4 font-medium">
                      Invoice
                    </th>
                    <th scope="col" className="py-2.5 pr-4 font-medium">
                      Date
                    </th>
                    <th scope="col" className="py-2.5 pr-4 font-medium">
                      Status
                    </th>
                    <th scope="col" className="py-2.5 pr-4 text-right font-medium">
                      Amount
                    </th>
                    <th scope="col" className="py-2.5 text-right font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <th scope="row" className="py-3 pr-4 text-left font-normal">
                        {invoice.number ?? invoice.id}
                      </th>
                      <td className="py-3 pr-4 tabular-nums text-muted-foreground">
                        {formatDate(invoice.created_at)}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={STATUS_VARIANTS[invoice.status] ?? "outline"}>
                          {invoice.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-right tabular-nums">
                        {formatCents(invoice.amount_paid_cents, invoice.currency)}
                      </td>
                      <td className="py-3 text-right">
                        <div className="flex justify-end gap-1">
                          {invoice.hosted_invoice_url && (
                            <Button variant="ghost" size="sm" asChild>
                              <a
                                href={invoice.hosted_invoice_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <ExternalLink className="size-3.5" aria-hidden="true" />
                                <span className="sr-only">
                                  View invoice {invoice.number ?? invoice.id}
                                </span>
                              </a>
                            </Button>
                          )}
                          {invoice.invoice_pdf_url && (
                            <Button variant="ghost" size="sm" asChild>
                              <a href={invoice.invoice_pdf_url} download>
                                <Download className="size-3.5" aria-hidden="true" />
                                <span className="sr-only">
                                  Download invoice {invoice.number ?? invoice.id} as PDF
                                </span>
                              </a>
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export function PaymentMethodsPanel({
  methods,
  onManage,
  canManage,
}: {
  methods: PaymentMethod[] | null;
  onManage?: () => void;
  canManage: boolean;
}): React.JSX.Element | null {
  if (methods === null) return null;

  return (
    <Card className="gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="font-medium">Payment methods</h2>
          <p className="text-sm text-muted-foreground">
            Cards are held by our payment provider. AgentVerse never sees or
            stores card numbers.
          </p>
        </div>
        {canManage && onManage && (
          <Button variant="outline" onClick={onManage}>
            <ExternalLink className="size-4" aria-hidden="true" />
            Manage
          </Button>
        )}
      </div>

      {methods.length === 0 ? (
        <p className="py-2 text-sm text-muted-foreground">
          No payment method on file.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {methods.map((method) => (
            <li key={method.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <CreditCard className="size-4 text-muted-foreground" aria-hidden="true" />
                <div>
                  <p className="text-sm capitalize">
                    {method.brand ?? "Card"} ···· {method.last4 ?? "????"}
                  </p>
                  {method.exp_month && method.exp_year && (
                    <p className="text-xs tabular-nums text-muted-foreground">
                      Expires {String(method.exp_month).padStart(2, "0")}/{method.exp_year}
                    </p>
                  )}
                </div>
              </div>
              {method.is_default && <Badge variant="secondary">Default</Badge>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
