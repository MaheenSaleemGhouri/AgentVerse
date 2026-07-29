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
| **Contrast measurement** | **Not run.** The tokens are the shared AVDS semantic ramps used across the product, not values Phase 6 introduced, so they are very likely already compliant — but "likely" is not a measurement, and none was taken for this audit |
| **Reduced-motion verification** | **Not run.** The only animation is `StatusBadge`'s pulse, already gated behind `motion-safe:` in code; the emulated-setting check was not performed |

None of these are blocked — they need a browser session and a person at
the keyboard, which this audit did not include.

## Target size

WCAG 2.2 AA (2.5.8) requires 24×24 CSS px minimum. Icon-only buttons use
`size-icon-sm` = 32×32. The house standard in `CLAUDE.md` §15 is 44×44,
which the icon buttons do not meet; they are within the tap-target
exception for pointer-adjacent controls on a desktop-first surface and
exceed the AA requirement. Recorded as a deliberate deviation from the
internal standard rather than passed over silently.

## Verdict

**Not a full WCAG 2.2 AA sign-off.** What this audit establishes:

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
