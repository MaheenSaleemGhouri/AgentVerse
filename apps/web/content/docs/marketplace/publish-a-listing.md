---
title: Publish a listing
summary: Put one of your agents in the public catalog, from draft through review to published.
pillar: marketplace
last_verified: "2026-08-07"
status: published
order: 2
---

Publishing puts a copy of one of your agents in the public catalog, where anyone can install it. This guide covers the lifecycle: draft, submit, review, published.

## Prerequisites

- A published agent worth sharing.
- `admin` or higher — publishing is a public act on behalf of the workspace.

## Create the listing

A listing needs a title, a one-line summary, a longer description, and a category. The summary is what appears in the catalog and in search results; it is the only thing most people read before deciding whether to look further.

Listings start as **drafts**. A draft is visible only to your workspace — it does not appear in the catalog, in search, or at its own URL for anyone else. A draft URL that someone outside guesses returns 404 rather than 403, so unpublished work cannot be found by probing.

## Readiness

Submitting checks the listing is complete: title, summary, description, category, and at least one version whose configuration can actually be installed. Anything missing is reported as a list, not one error at a time.

## Submit for review

Submitting moves the listing to **pending**. A platform administrator approves or rejects it. Approval publishes it; rejection returns it to draft with a reason, and you can fix and resubmit.

Review exists because installing runs someone else's instructions in your workspace. That warrants a look by a person.

## Versions

A listing has versions. Publishing a new one does not change anything for people who already installed an older one — an install is a copy, and copies do not update themselves. Installers choose when to take a new version by installing again.

## Pricing

A listing records a price, and the catalog shows it.

> **Not yet enforced.** Payment for paid listings is not implemented: a listing with a non-zero price installs without charging. Do not rely on the price field as a paywall — it is displayed, not collected. Publish paid listings only when you are content for them to be installed for free until this ships.

## Reviews and ratings

Installers can rate and review a listing. You cannot review your own — the check is server-side, so it holds for API callers too.

## Expected result

An approved listing visible in the catalog, findable by search, and installable by anyone.

## Troubleshooting

**Submitting was refused.** The readiness check lists what is missing.

**The listing was rejected.** The reason comes back with it. Fix and resubmit; there is no limit on attempts.

**Your listing does not appear in search.** Only published listings are searchable. Drafts and pending listings are excluded.

**Workflow listings are refused.** Only agent listings exist today. The workflow kind is defined but inert until the DAG workflow builder ships, and attempting one is refused explicitly rather than accepted and quietly ignored.

## Related guides

- [Install a template](/docs/marketplace/install-a-template)
- [Roles and permissions](/docs/platform/roles-and-permissions)
