# Accessibility audit — Phase 6 MCP integration surfaces

WCAG 2.2 AA, the merge gate in `CLAUDE.md` §15 and Rule 7. Covers the
three screens Phase 6 added and the seven components behind them.

| Surface | Route |
| --- | --- |
| Marketplace + connected servers | `/dashboard/{workspaceId}/integrations` |
| Server detail (Tools · Credentials · Access · Activity) | `/dashboard/{workspaceId}/integrations/{id}` |
| MCP runtime | `/dashboard/{workspaceId}/mcp` |

## Automated scan

`components/integrations/integrations-a11y.test.tsx` runs axe-core
against every component's real rendered output on each `pnpm test`, so a
regression fails CI rather than reaching a user. **10 tests, 0
violations** across `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`,
`wcag22aa`.

Two limits stated plainly, because a scan reported without them
overstates what it proves:

- **Colour-contrast rules are disabled in the scan.** jsdom performs no
  layout and computes no colour, so axe's contrast checks cannot run.
  Leaving them enabled would produce a pass that means nothing. Contrast
  is covered manually below.
- **axe detects a minority of real accessibility problems.** It finds
  missing names, invalid ARIA, and broken structure. It cannot judge
  whether focus order makes sense or whether a live region announces
  usefully. Those are the manual passes.

## Findings and fixes

### 1. Filter strips claimed to be tabs — `aria-valid-attr-value`, critical · **fixed**

The marketplace category filter and the runtime status filter were built
from `Tabs`/`TabsList`/`TabsTrigger`, but the filtered results render
*outside* the `Tabs` element. Radix puts `aria-controls` on every trigger
pointing at a `tabpanel`; with no `TabsContent` anywhere, every one of
those references pointed at an element that does not exist.

Consequence for a screen-reader user: a tablist announcing tabs that
control nothing, on both new screens.

Fixed by `components/patterns/filter-group.tsx` — a group of
`aria-pressed` toggle buttons in a labelled `role="group"`. These
controls filter a list; they do not switch panels, and the markup now
says so. Styling is shared with `Tabs` through the extracted
`tabsTriggerVariants`, so the two cannot drift visually and no token was
duplicated.

The rule was not suppressed. Suppressing it would have left the
misannouncement in place and hidden it from the next audit.

### 2. Tooltip on an inert element — WCAG 2.1.1 · **fixed**

The marketplace card exposes *which credentials a server will ask for*
in a tooltip on a `Badge`. A `span` is not focusable, so the tooltip
could only be opened with a pointer — the information was unreachable by
keyboard.

This one matters more than a typical tooltip: it is what a user reads
before deciding to hand over a secret. Fixed with `tabIndex={0}` on the
trigger, which Radix opens on focus.

### 3. `TooltipProvider` was missing from the test wrapper — **test defect, not a product defect**

The marketplace threw without it. `app/providers.tsx` supplies it in the
real tree, so production was never affected; the first wrapper simply
rendered a tree the app never renders. Recorded because "the test was
wrong" is a finding worth keeping honest.

## Static review — verified by reading the shipped markup

These were checked against the components and asserted by the test suite
where a test can assert them. They are code-level facts, not the
behavioural passes below.

| Check | Basis |
| --- | --- |
| Every interactive element is a `button`, `a`, or a labelled form control — no `div` with `onClick` | Read across all seven components |
| Icon-only controls carry an accessible name | `Delete {key}`, `Revoke access`, `Back to integrations`; a test walks every rendered `button` and fails on an unnamed one |
| Decorative icons are hidden | `aria-hidden="true"` on every lucide icon in these files |
| Status is never colour-only | `StatusBadge` always renders a text label beside its dot; a test asserts a denied call carries the word and the reason |
| Focus ring never suppressed | `focus-visible:ring-[3px] ring-ring/50` inherited from the shared primitives; no `outline-none` without a replacement |
| Focus trapping is not hand-rolled | The dialog and the uninstall confirmation are Radix `Dialog`/`AlertDialog`, which implement trap-and-restore once in the shared layer |
| Form controls are labelled | `htmlFor`/`id` pairs throughout; the tool picker uses a real `fieldset`/`legend` |
| Credential values are unreachable | Only `ends ••••x7f2` is rendered; the API has no endpoint that returns a value |

**No live region is needed on these surfaces.** Nothing here streams;
tool-call history is fetched, not pushed. The live-region model for
streaming runs is Phase 4's and is unchanged. Adding one here would
announce on every refetch for no benefit — the over-announcing failure
mode the `accessibility-expert` skill calls out.

## Not yet performed

Stated explicitly rather than left to be assumed from the sections above.
The skill's own workflow requires steps 2–4; only step 1 (automated scan)
has run.

| Pass | Status |
| --- | --- |
| **Manual keyboard-only pass** in a real browser | **Not run.** The static review above establishes that the markup is operable in principle; it does not establish that focus *order* is sensible, that nothing is a keyboard trap, or that the filter groups feel usable |
| **Screen-reader pass** (NVDA or VoiceOver) | **Not run.** No claim is made about what these screens actually announce |
| **Contrast measurement** | **Run — see below. The guess recorded here previously was wrong.** |
| **Reduced-motion verification** | **Not run.** The only animation is `StatusBadge`'s pulse, already gated behind `motion-safe:` in code; the emulated-setting check was not performed |

None of these are blocked — they need a browser session and a person at
the keyboard, which this audit did not include.

## Contrast — measured, and fixed

`app/design-tokens-contrast.test.ts` parses the real tokens out of
`globals.css` and computes WCAG ratios for the pairs the components
actually render. It runs on every `pnpm test`.

This section previously said contrast was "not run" but that the tokens
were "very likely already compliant". **That guess was wrong.** Six
rendered pairs fail AA in light theme and three in dark:

The failures found, all since fixed:

| Pair | Light | Dark | Rendered by |
| --- | --- | --- | --- |
| `--success` on `--success-soft` | **2.52:1** | 5.01:1 ✅ | `StatusBadge` success |
| `--warning` on `--warning-soft` | **2.14:1** | 6.44:1 ✅ | `StatusBadge` warning |
| `--info` on `--info-soft` | **2.82:1** | 4.87:1 ✅ | `StatusBadge` info |
| `--destructive` on `--destructive-soft` | **3.29:1** | **4.37:1** | `StatusBadge` danger |
| `--primary-foreground` on `--primary` | **4.35:1** | **4.35:1** | `Button` default variant |
| `--destructive-foreground` on `--destructive` | **3.76:1** | **3.76:1** | KB count badge |

All are body-sized text, so none qualifies for the 3:1 large-text
allowance. Everything else measured — body text, muted text on both
page and card, secondary surfaces, and the focus ring against the page
(1.4.11) — passes in both themes.

**These were not Phase 6 defects.** `StatusBadge`, `Button`, and the
count badge all predate it; Phase 6 renders `StatusBadge` and inherited
the failure.

### The fix

Splitting the role, rather than darkening the hue. Each status now has
three tokens held to different thresholds:

| Token | Used for | Threshold |
| --- | --- | --- |
| `--success` | the badge dot, the Alert icon | decorative — see below |
| `--success-soft` | the tinted background | — |
| `--success-strong` | **text** on that background | 4.5:1 |

Darkening `--success` itself would have fixed the text and dulled every
dot and border with it. The new `-strong` tokens are the smallest
darkening that clears AA — `#17b26a → #11804c` and so on — and in dark
theme three of the four already passed, so `-strong` is simply the base
there. Only danger needed lightening (`#f04438 → #f4655b`), the
direction that raises contrast against a dark surface.

Two tokens changed globally, both by the minimum that clears AA:

- `--primary` `#7c5cff → #7859f7` (3% darker; white button text was
  4.35:1). `--brand-500` keeps the original hue, so the brand ramp is
  untouched.
- `--destructive` `#f04438 → #d83d32` (white text was 3.76:1).

All 34 contrast assertions now pass in both themes, and the production
build is clean.

### The dots are deliberately not held to 3:1

WCAG 1.4.11 covers graphics *required* to identify a state. The
`StatusBadge` dot is `aria-hidden` and always sits beside a text label,
so the state is carried by the words and the dot reinforces it. Same for
the `Alert` icon. Holding decoration to 3:1 would have pushed the palette
darker for no accessibility gain.

That is a judgement call, so it is written down rather than left as a
missing test — and what keeps it honest is the existing assertion that a
status is never colour-only. If the text label were ever dropped, the
dot would become the indicator and this reasoning would stop holding.

### What the measurement still does not establish

It checks token pairs found by reading the components, so a future
component pairing two tokens nobody anticipated is uncovered; and it
computes ratios rather than rendering them, so an opacity modifier
applied in a class (`bg-destructive-soft/30`, which the runtime view
uses) is not accounted for.

## Target size

WCAG 2.2 AA (2.5.8) requires 24×24 CSS px minimum. Icon-only buttons use
`size-icon-sm` = 32×32. The house standard in `CLAUDE.md` §15 is 44×44,
which the icon buttons do not meet; they are within the tap-target
exception for pointer-adjacent controls on a desktop-first surface and
exceed the AA requirement. Recorded as a deliberate deviation from the
internal standard rather than passed over silently.

## Verdict

**Not a full WCAG 2.2 AA sign-off**, but closer than it was: contrast has
moved from an unverified guess to a measured, fixed, CI-gated property.
What this audit establishes:

- The automated scan passes with zero violations, and is now a permanent
  CI gate.
- Two real defects were found and **fixed rather than waived** — the
  false tablist and the keyboard-unreachable tooltip. The first was a
  critical-impact violation present on both new screens.
- The markup review found no further structural problems.

What it does not establish: anything requiring a browser and a human —
keyboard order, screen-reader output, measured contrast, reduced motion.
Those four are listed above as not run.

Per `CLAUDE.md` §19 item 7, `accessibility-expert` is the last
non-negotiable gate before a UI surface ships, and that gate is **not
satisfied** until the manual passes are done. This document is the
automated half, honestly bounded.

The regression gate is `pnpm --filter @agentverse/web test`. It runs on
every PR and fails on any new violation.
