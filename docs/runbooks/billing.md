# Runbook: billing alerts

Every alert in the `agentverse-billing` group links here. Each section
follows the same shape: what fired, what it actually means, what to do,
and — importantly — what *not* to do.

The selection criterion for these alerts is worth restating, because it
explains why some obvious things are missing: **each covers a failure
that is otherwise silent.** A failed customer payment is not here, and
that is deliberate — it already produces a dunning email, an in-app
notification, and a visible `past_due` status. It needs no page.

---

## Webhook processing failure

`BillingWebhookProcessingFailures` — P1, platform-oncall.

### What it means

A provider webhook was verified and claimed, and then the handler
raised. The row in `billing_webhook_events` is sitting at
`status = 'failed'` with the exception recorded in `error`.

`duplicate` and `ignored` are **successes**, not failures. A redelivered
event and an event type this system does not act on both have their own
outcomes. `failed` means the handler genuinely raised.

### Why it is P1 despite the provider retrying

The provider will retry, so this may resolve itself. But until it does,
the subscription has not transitioned — a customer who paid may not be
marked active, or one whose payment failed may not have entered dunning.
Neither produces a visible symptom until an invoice is wrong.

### What to do

```sql
SELECT provider_event_id, event_type, workspace_id, error, received_at
FROM billing_webhook_events
WHERE status = 'failed'
ORDER BY received_at DESC
LIMIT 20;
```

The `error` column names the exception. The common causes, in order of
likelihood:

1. **`PlanNotFoundError` / `CatalogIncompleteError`** — a plan was
   deactivated in the `plans` table while subscriptions still reference
   it. Reactivate it; do not edit the subscription.
2. **`InvalidTransitionError`** — out-of-order delivery. The handler
   already refuses these rather than forcing the state machine, so a
   *failure* here means an unexpected shape. Check the event's
   `occurred_at` against the subscription's history.
3. **A database error** — usually a constraint. Read which one; every
   billing constraint encodes an invariant and the violation names it.

### What not to do

- **Do not manually transition the subscription.** The webhook is
  idempotent by `provider_event_id`; let the retry do it. A manual
  transition consumes the idempotency key and the retry then does
  nothing, leaving the event log claiming something that did not happen.
- **Do not delete the failed row** to "clear" the alert. It is the only
  record that the event was received.

---

## Credit drift

`BillingCreditDrift` — P1, platform-oncall.

### What it means

Reconciliation found a workspace whose `billing_credits.balance_cents`
does not equal the sum of its `billing_credit_transactions`.

This should be impossible. The balance is only ever written in the same
transaction as its ledger row, under `SELECT ... FOR UPDATE`. A
disagreement means **something wrote a balance outside that path.**

### What to do

```sql
SELECT c.workspace_id, c.balance_cents,
       COALESCE(SUM(CASE
         WHEN t.reason IN ('referral_reward','coupon_redemption','promotional_grant',
                           'refund_to_account','support_adjustment')
         THEN t.amount_cents ELSE -t.amount_cents END), 0) AS ledger_cents
FROM billing_credits c
LEFT JOIN billing_credit_transactions t ON t.workspace_id = c.workspace_id
GROUP BY c.workspace_id, c.balance_cents
HAVING c.balance_cents <> COALESCE(SUM(CASE
         WHEN t.reason IN ('referral_reward','coupon_redemption','promotional_grant',
                           'refund_to_account','support_adjustment')
         THEN t.amount_cents ELSE -t.amount_cents END), 0);
```

Then find **what wrote it** — a migration, a manual `UPDATE`, a support
script. That is the incident; the number is a symptom.

### What not to do

**Do not "fix" the balance to match the ledger and close the ticket.**
The ledger is the truth, so correcting the balance is the right *repair*
— but doing it before finding the writer means it will happen again, and
next time nobody will be watching. Repair after diagnosis, and repair by
appending a compensating ledger movement so the correction is itself
auditable. Never by a bare `UPDATE`.

---

## Quota refusal spike

`QuotaRefusalSpike` — P2, platform-oncall.

### What it means

Customers are being refused at more than 5× the same hour last week.

One refusal is the feature working: a workspace hit a hard limit on a
plan with no overage rate, and was correctly stopped. Every individual
refusal looks correct, which is exactly why only the aggregate can show
a problem.

### What to do

Split the metric by its `dimension` label to see which limit is
involved. Then, in order:

1. **Was a plan edited?** `plans` is edited operationally, not by
   deploy, so a limit can change without a release.
   ```sql
   SELECT slug, display_name, metered_allowances, updated_at
   FROM plans ORDER BY updated_at DESC;
   ```
2. **Did a new dimension start recording?** A metered dimension that
   began producing usage against an allowance nobody set for it will
   refuse everything on plans with a low default.
3. **Is it one workspace or many?** One is a customer who needs an
   upgrade prompt; many is our configuration.

### What not to do

Do not raise limits to silence the alert. If the limits are wrong, that
is a pricing decision (`saas-pricing-expert`), not an ops one.

---

## Payment provider errors

`PaymentProviderErrors` — P2, platform-oncall.

### What it means

More than a fifth of calls to the payment provider are erroring.

**A card decline is not counted here.** A decline is a *successful* API
call — the provider answered. This alert means the provider is
unreachable, our key is wrong, or a request shape was rejected.

### What to do

1. Check the provider's status page before anything else.
2. Check whether the key is still valid — a rotated or revoked key
   produces exactly this.
3. Check the `retryable` flag on the errors in the logs. `ProviderError`
   carries it, and a non-retryable error at volume is our request
   shape, not their availability.

Customers cannot start checkout or open the billing portal while this
fires. Existing subscriptions are unaffected — they renew at the
provider, not through us.

---

## Notification delivery failures

`NotificationDeliveryFailures` — P3, platform-oncall.

### What it means

More than a tenth of transactional emails failed to send. The in-app
notifications are unaffected — they are recorded first and separately,
which is why this is P3 rather than P1.

### Why it still matters

Dunning depends on the inbox. A customer who is never told their card
failed will be canceled at the end of the retry window without ever
having seen a warning.

### What to do

```sql
SELECT n.kind, d.address, d.error, d.created_at
FROM notification_deliveries d
JOIN notifications n ON n.id = d.notification_id
WHERE d.status = 'failed'
ORDER BY d.created_at DESC LIMIT 20;
```

**Note the current state of this system honestly:** no transactional
email vendor is configured, and the adapter logs instead of delivering.
So in the current deployment this alert firing means something other
than a vendor outage — most likely the logging adapter itself raising,
which would be a code problem. Once a vendor is wired, the usual causes
apply (auth failure, rate limit, bad address).

### What not to do

Do not re-run the notification to force a resend. The delivery claim is
unique per `(notification_id, channel)`, so a manual retry is a no-op —
and if you delete the delivery row to work around that, you lose the
record that the send was attempted at all.
