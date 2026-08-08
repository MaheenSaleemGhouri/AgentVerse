# AgentVerse Design Reference

## Master Reference

**File:** [`agentverse-master-design-reference.png`](./agentverse-master-design-reference.png)

**Status:** **APPROVED**

**Purpose:** Primary visual source of truth for the AgentVerse UI implementation.

---

### mascot-reference.png

**File:** [`mascot-reference.png`](./mascot-reference.png)

**Status:** **APPROVED**

**Purpose:** Official AgentVerse Robot / Mascot visual reference.

This asset is the single source of truth for the AgentVerse mascot.

Where it and panel 03 of the master reference differ in the mascot's
proportions, **this file governs** — the master sheet remains the source
of truth for everything else. The mascot rules extracted from it are in
[`design-system.md` §6](./design-system.md).

Keep this file untouched: do not compress, recolour, crop, or overwrite
it. Production-ready transparent mascot assets, when they are needed,
are created as separate files.

---

## What it covers

The reference is a fifteen-panel sheet. Every panel is approved visual
direction, not a mood board:

| # | Panel | Covers |
|---|---|---|
| 01 | Brand Guidelines | Logo lockup, colour palette, shadow scale, border-radius scale, button treatment |
| 02 | Typography Guide | The three locked typefaces and their roles, with rendered specimens |
| 03 | Mascot Reference | The AgentVerse robot — poses, proportions, material, expression set |
| 04 | Auth Reference | Sign-in and sign-up screens |
| 05 | Dashboard Reference | Main dashboard: sidebar, stat row, usage chart, activity feed |
| 06 | Agent Builder Reference | Node canvas, node settings panel, test panel, logs |
| 07 | Knowledge Reference | Knowledge-base stats, file table, tab navigation |
| 08 | MCP Reference | MCP marketplace: category rail, tool cards, installed list |
| 09 | Workflow Reference | Workflow canvas and node properties panel |
| 10 | Analytics Reference | Stat row, line chart, donut chart, export control |
| 11 | Team Reference | Members table, roles, permissions, activity tabs |
| 12 | Billing Reference | Plan card, usage meters, invoice table |
| 13 | Settings Reference | Settings nav, form layout, API-key fields |
| 14 | Mobile Reference | Mobile app screens — dashboard, agents, chat, analytics, menu |
| 15 | UI Showcase | 20+ screen overview, for density and consistency calibration |

---

## How to use it

Before implementing any UI screen:

1. Read this file.
2. Read [`design-system.md`](./design-system.md) — the written rules extracted from the reference.
3. Inspect [`agentverse-master-design-reference.png`](./agentverse-master-design-reference.png) — the panel relevant to the screen you are building.
4. Reuse existing AVDS components (`apps/web/components/ui/`, `apps/web/components/patterns/`) wherever one fits.
5. Do not invent a new visual language.

The goal is a technically correct, responsive implementation that stays
visually faithful to the reference — not a pixel-for-pixel trace. Where
responsive behaviour requires adaptation, adapt the layout and keep the
design language.

---

## Scope of this document

This directory is design reference only. Registering it changed no
application code: no component, token, font, route, or backend was
modified. See the **Conformance status** section of `design-system.md`
for where the shipped product currently differs from the reference —
that section is a record, not a work order.
