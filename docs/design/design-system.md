# AgentVerse Design System — Approved Specification

Extracted from [`agentverse-master-design-reference.png`](./agentverse-master-design-reference.png).
That image is the source of truth; this file is the written form of the
rules visible in it, so they can be cited in review and diffed over time.

**Brand:** AgentVerse
**Design language version:** v1.0 (as labelled in panel 01)
**Status:** APPROVED

---

## 1. Visual direction

- Premium
- Professional
- Warm
- Minimal
- Enterprise SaaS
- Human-centered AI
- Clean whitespace
- Soft surfaces
- Subtle borders
- Refined rounded components
- Controlled use of shadows
- Calm visual hierarchy

The register is restraint. Nothing in the reference decorates: every
shadow, border, and tint is doing a job — separating a surface, marking
a state, or grouping a set. A gradient, a heavy shadow, or an animation
that cannot name its function does not belong on a screen built from
this system.

---

## 2. Colour — the locked palette

| Role | Hex | Notes |
|---|---|---|
| Primary | `#463F3A` | Warm near-black. Primary buttons, active nav, headings. |
| Secondary | `#8A817C` | Warm mid-grey. Secondary text, muted labels, inactive states. |
| Border | `#BCB8B1` | Warm light grey. Dividers, card borders, input outlines. |
| Background | `#F4F3EE` | Warm off-white. Page ground. |
| Accent | `#E0AFA0` | Muted terracotta. The single warm highlight — secondary CTAs, selected states, chart emphasis. |

**Rules:**

- Do not introduce a different primary colour system. The warm-neutral
  family above is the identity.
- Semantic colours — success, warning, error, info — may exist where
  they are functionally necessary (a failed run must not read as a
  successful one). They must be tuned to harmonise with this palette:
  desaturated toward the warm neutral ground, never a stock traffic-light
  set dropped in unmodified.
- Status is never colour alone. Every status pairs colour with an icon
  or a text label (WCAG 2.2 AA; `CLAUDE.md` §15).
- Every colour resolves to a token. No raw hex in component markup.

**Palette hierarchy in use, as the reference shows it:** background
`#F4F3EE` carries the page; cards sit on it in white or a lighter warm
tint; `#BCB8B1` draws the boundary between them; `#463F3A` carries
weight — headings, primary actions; `#8A817C` recedes — metadata,
secondary copy; `#E0AFA0` appears sparingly and therefore reads as
emphasis.

---

## 3. Typography — the locked stack

| Role | Typeface |
|---|---|
| Headings | **Satoshi** |
| UI / Body | **Geist** |
| Technical / Code | **JetBrains Mono** |

As specified in panel 02: Satoshi Bold at 48px for a hero heading,
Satoshi Medium at 24px for a section title, Geist Regular at 16px for
body copy, JetBrains Mono for code blocks and technical values.

**Rules:**

- Use these three consistently. Do not substitute arbitrary fonts.
- Headings are Satoshi; body, form, table, and navigation text is Geist.
  The split is by role, not by page.
- JetBrains Mono is for code, IDs, keys, and technical values — not for
  general UI.

---

## 4. Shape, depth, and spacing

**Border radius** — the reference shows a four-step scale: `8px`,
`12px`, `16px`, `24px`. Smaller steps for inputs, buttons, and badges;
larger for cards, panels, and modals. Radius is consistent within a
component family, never mixed inside one card.

**Shadows** — a four-step scale (`sm`, `md`, `lg`, and one heavier
step), used sparingly. Elevation in this system comes mostly from
surface lightness and border, with shadow as a light accent. A card is
separated by its border first and its shadow second.

**Spacing** — a 4px base unit (4, 8, 12, 16, 24, 32, 48, 64, 96). The
reference's density is generous but not loose: dense data surfaces
(tables, canvases, log panels) tighten, while forms, settings, and
marketing surfaces breathe.

---

## 5. Component treatment

Read from the reference panels; these are the rules a new screen must
match.

**Cards** — white or light warm surface, subtle `#BCB8B1` border,
generous internal padding, radius from the scale. Stat cards show a
label, a large value, and a delta with direction.

**Buttons** — primary is solid `#463F3A` with light text; secondary is
an outlined/ghost treatment on the warm ground; the accent treatment
uses `#E0AFA0` and is reserved, not a second primary. One action per
CTA.

**Forms** — labelled inputs stacked vertically, subtle border, clear
focus ring, helper and error text below the field. Selects and
dropdowns share the input's shape and border.

**Navigation** — a dark, fixed left sidebar with an icon-plus-label
list, a clear active state, the product mark at the top and the user
identity at the bottom. Content sits on the warm ground to its right.

**Tables** — quiet header row, generous row height, left-aligned text,
right-aligned numerics, status as a badge, row actions at the trailing
edge.

**Charts** — thin strokes, restrained fills, muted palette drawn from
the brand neutrals plus the accent. Axis and grid recede; the data
carries. Donuts carry a centred total.

**Canvases** (agent builder, workflow builder) — nodes are small
bordered cards on a subtle grid, connected by soft curved edges, with a
properties panel docked to one side.

**Every interactive component defines all its states** — default, hover,
active, focus, disabled, loading, error, empty. A screen designed only
for the happy path with data is unfinished.

---

## 6. The AgentVerse mascot

**Source of truth:** [`mascot-reference.png`](./mascot-reference.png) —
status **APPROVED**. Where it and panel 03 of the master sheet differ in
proportion, the dedicated mascot reference governs.

The approved mascot is a **friendly white humanoid AI robot**.

### Visual characteristics

- White premium body
- Rounded futuristic construction
- Glossy black expressive face/visor
- Friendly facial expressions
- Warm metallic/beige accent details
- AgentVerse logo/emblem on the chest
- Clean premium appearance
- Minimal futuristic aesthetic
- Welcoming personality

The character reads as approachable before it reads as technological:
a large rounded head, a soft matte shell with visible segmented joints,
and a glossy black visor carrying simple bright eyes and a smile. The
warm beige accents tie it to the brand accent (`#E0AFA0`) rather than to
a cold chrome palette — that warmth is part of the identity, not
decoration.

### Approved reference views

- Front
- Side
- Back
- Happy
- Thinking
- Excited
- Helping
- Laptop interaction
- Welcoming gesture

### Consistency rule

Future UI implementations **must** reuse this mascot design.

Do **not**:

- Create a different robot
- Change the robot's proportions
- Change its core colours
- Replace it with a generic AI avatar
- Use unrelated 3D characters
- Create a cyberpunk robot
- Create a cartoon robot with a different visual identity

Expressions and poses **may** change where UX requires it — a new pose
is fine, a new character is not. The underlying mascot identity stays
consistent with the approved reference.

### Where the mascot may appear

- Login
- Signup
- Onboarding
- Dashboard
- Agent Builder
- AI Assistant
- Empty states
- Loading states
- Success states
- Error states
- Help Center
- Documentation
- Marketplace
- Knowledge Base
- Analytics
- Billing
- Product guidance
- Marketing surfaces

**Use it intentionally — do not force it into every component.** The
mascot supports the interface; it never obstructs it. On dense working
surfaces (canvas, log viewer, tables) it appears small or not at all.
Where it carries no information it is decorative, and decorative imagery
is marked `aria-hidden` so a screen reader is not made to describe it.

### Asset handling

`mascot-reference.png` is kept untouched — never compressed, recoloured,
cropped, or overwritten. Production-ready transparent mascot assets are
created as **separate files** when they are needed.

*Note for whoever reads the reference later: several text labels in the
image are garbled by the generation that produced it ("Heloing",
"Flappy", "AgentVerce Lago"). The **robot renders** are the approved
content; the label text is not authoritative. The expression names are
the ones listed above.*

---

## 7. Light and dark mode

Both modes are first-class and equally composed.

**Rule:** dark mode is designed, never a CSS inversion. Inverting this
palette produces cold grey, which loses the warmth that is the identity.
The dark theme keeps the same warm bias — warm dark surfaces, warm
neutral text, the same accent — and builds elevation from **border plus
surface lightness**, not shadow, which barely reads on a dark ground.

The identity must be recognisably AgentVerse in both modes: same
hierarchy, same shapes, same mascot, same accent used with the same
restraint. Contrast thresholds (4.5:1 body, 3:1 large text and UI) apply
to both, measured independently.

---

## 8. Responsive design

The reference includes desktop (panels 04–13) and mobile (panel 14)
direction. Implementation must support **desktop, tablet, and mobile** —
desktop-only layouts are not acceptable.

Responsive behaviour preserves the design language while adapting:

- **Navigation** — sidebar collapses to a drawer or bottom bar; the
  active state stays legible.
- **Sidebar** — icon-only at intermediate widths, off-canvas on mobile.
- **Cards** — multi-column grids reflow to a single column.
- **Tables** — scroll horizontally inside their own container, or
  restructure into stacked rows. The page body never scrolls sideways.
- **Charts** — reflow and reduce labelling rather than shrinking to
  illegibility.
- **Forms** — single column, full-width controls, comfortable tap
  targets (44×44px minimum).
- **Agent Builder / Workflow Builder** — desktop- and tablet-first, with
  a documented minimum viewport below which they degrade to a simplified
  read-only view. Never a broken canvas.
- **Marketplace / Dashboards** — fully responsive to mobile.

---

## 9. Conformance status

*A record of where the shipped product currently stands against this
reference, so review can tell "not yet aligned" from "regressed". This
section is not a work order and nothing here was changed by registering
the reference.*

| Area | Reference | Shipped today (`apps/web`) | Aligned |
|---|---|---|---|
| Palette | Warm neutrals — `#463F3A`, `#8A817C`, `#BCB8B1`, `#F4F3EE`, `#E0AFA0` | The approved palette, in `globals.css`. Zero purple remains in the built bundle. | ✅ |
| Heading font | Satoshi | Satoshi, self-hosted via `next/font/local` from `app/fonts/`, applied to `h1–h3` in the base layer | ✅ |
| Body font | Geist | Geist | ✅ |
| Code font | JetBrains Mono | JetBrains Mono is now `--font-mono` product-wide, with Geist Mono as its fallback | ✅ |
| Radius scale | 8 / 12 / 16 / 24px | `--radius: 0.75rem` (12px) with derived steps | ✅ |
| Spacing | 4px base | Tailwind v4 default 4px scale | ✅ |
| Tokenisation | Every value a token | `@theme` tokens in `globals.css`; no raw hex in markup | ✅ |
| Dark mode | Designed, warm | Designed warm — `#1a1715` ground, warm surfaces, elevation from border + lightness | ✅ |
| Status colours | Harmonised with the warm palette | Desaturated toward the warm ground; all pairs measured | ✅ |
| Sidebar | Dark rail in both themes | Own token set (`--sidebar-*`), dark in light and dark mode | ✅ |
| Mascot | The approved white humanoid robot (`mascot-reference.png`) | CC0 placeholder — `public/models/robot.glb` on the auth scene, and a simple 2D SVG mark on the assistant launcher. Neither is the approved character. | ❌ |
| Responsive | Desktop / tablet / mobile | Shell: full sidebar ≥1024, icon rail at 768, drawer below | ✅ |
| Accessibility | WCAG 2.2 AA | AA a merge gate; 40 contrast pairs asserted in CI | ✅ |

### How the approved palette maps to roles

The five approved values are used in the roles the reference *draws*
them in, which is not always the role their name suggests. Two of them
cannot be text colours at all:

| Value | Measured as text on `#F4F3EE` | Role it actually has |
|---|---|---|
| `#463F3A` | 9.30:1 ✅ | Body text, primary fills, focus ring |
| `#8A817C` | 3.43:1 ❌ | Form-control outlines (3:1 non-text bar) — never text |
| `#BCB8B1` | 1.78:1 ❌ | Dividers and card edges — decoration |
| `#E0AFA0` | 1.75:1 ❌ | Solid accent fill; its label is `#463F3A` at 5.32:1 |

Text-carrying variants are derived from the same hues
(`--muted-foreground: #6b635c`, `--accent-foreground: #7c4a37`), exactly
as the status tokens already split `--success` from `--success-strong`.
`app/design-tokens-contrast.test.ts` measures all 40 pairs from the real
file and fails on drift — including the two that are easiest to get
wrong: white on the accent fill (1.94:1, forbidden) and any attempt to
lighten `--input`, which clears its bar at 3.43:1 with little room.

### One role that flips between themes

`--primary`. The approved `#463F3A` is a near-black, and a near-black
fill on a dark ground is invisible, so dark mode takes the warm light
end of the same ramp. The accent does **not** flip — `#E0AFA0` works on
both grounds, and holding it fixed is part of what makes the two themes
read as one product.

### Satoshi — an earlier refusal, corrected

Earlier in Phase 10 I declined to add Satoshi, reasoning that changing
the body font would restyle every existing page. The reference resolves
that: Satoshi is the **heading** font and Geist stays the body font — a
materially smaller change than the one I refused. Recorded so the older
reasoning is not cited later as if it still applied.

The mascot delta is a sourcing question, not an implementation one — the
approved character has to exist as a production asset before it can be
used.
