/**
 * @vitest-environment node
 *
 * Node, not jsdom: this reads a file and does arithmetic — no DOM is
 * involved. The default jsdom environment costs several seconds of
 * startup per file here, and spending it to render nothing is what
 * pushed the suite into worker-startup timeouts when this file was
 * added.
 *
 * WCAG 2.2 AA contrast, measured from the real tokens in `globals.css`.
 *
 * The Phase 6 accessibility audit originally listed contrast as "not
 * run" because the automated axe scan cannot check it — jsdom performs
 * no layout and computes no colour, so axe's contrast rules are
 * disabled there and would otherwise report a meaningless pass.
 *
 * That does not mean contrast can only be checked by eye. The tokens are
 * plain hex in `globals.css`, and the WCAG formula is arithmetic. Parsing
 * the real file and computing the real ratios is a *measurement*, and
 * unlike a one-off manual pass it stays true: a token edited to an
 * inaccessible value fails this test rather than shipping and waiting to
 * be noticed.
 *
 * What this does NOT cover, stated so the audit does not overclaim:
 * it checks token *pairs that are actually used together*, listed below
 * by reading the components. It cannot know that a future component
 * pairs two tokens nobody anticipated. That gap is what a browser-based
 * pass would close, and it remains open.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "globals.css"), "utf8");

/**
 * Extracts a `--token: value;` map from one CSS block.
 *
 * Anchored to the start of a line: `:root` and `.dark` are both named in
 * the file's header comment, and an unanchored search finds the prose
 * rather than the rule — which yields a short, plausible-looking token
 * map and a suite that passes on the handful of tokens it happened to
 * catch. The `parsed real tokens` assertion below exists for the same
 * reason.
 */
function tokensIn(selector: string): Record<string, string> {
  const start = new RegExp(`^${selector.replace(".", "\\.")}\\s*\\{`, "m").exec(CSS);
  if (!start) throw new Error(`no ${selector} rule in globals.css`);
  const block = CSS.slice(start.index);
  const body = block.slice(block.indexOf("{") + 1, block.indexOf("}"));
  const out: Record<string, string> = {};
  for (const line of body.split("\n")) {
    const match = /^\s*--([\w-]+):\s*([^;]+);/.exec(line);
    if (match?.[1] && match[2]) out[match[1]] = match[2].trim();
  }
  return out;
}

const LIGHT = tokensIn(":root");
const DARK = tokensIn(".dark");

/** sRGB relative luminance, WCAG 2.x definition. */
function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value;
  const channels = [0, 2, 4].map((i) => Number.parseInt(full.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!;
}

function contrast(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

function resolve(theme: Record<string, string>, name: string): string {
  const value = theme[name];
  if (!value) throw new Error(`token --${name} not found`);
  if (!value.startsWith("#")) throw new Error(`token --${name} is not a hex value: ${value}`);
  return value;
}

/**
 * Pairs read off the Phase 6 components, not invented. Each is a
 * foreground actually rendered on that background somewhere in
 * `components/integrations/`.
 *
 * `large` marks text at >=18.66px bold or >=24px, where AA drops to 3:1.
 * Nothing here claims that exemption — the dense surfaces this phase
 * added are all body-sized — so every pair is held to 4.5:1.
 */
const TEXT_PAIRS: ReadonlyArray<{ fg: string; bg: string; where: string }> = [
  { fg: "foreground", bg: "background", where: "page body text" },
  { fg: "foreground", bg: "card", where: "marketplace + server cards" },
  { fg: "muted-foreground", bg: "background", where: "descriptions, timestamps, empty states" },
  { fg: "muted-foreground", bg: "card", where: "card subtitles, tool descriptions" },
  { fg: "primary-foreground", bg: "primary", where: "button.tsx default variant" },
  { fg: "secondary-foreground", bg: "secondary", where: "filter group, secondary badges" },
  { fg: "destructive-foreground", bg: "destructive", where: "document-library.tsx count badge" },
];
// `--success-foreground`, `--warning-foreground`, and `--info-foreground`
// are deliberately absent: grepping the components shows nothing renders
// them. Asserting a pair the product never draws proves nothing and
// invites someone to "fix" a token no screen uses.

/**
 * Status text on its soft tinted background — the pattern StatusBadge
 * uses, and the one most likely to fail, since a soft tint sits close to
 * the page background by design.
 */
const STATUS_ON_SOFT: ReadonlyArray<{ fg: string; bg: string; where: string }> = [
  { fg: "success-strong", bg: "success-soft", where: "StatusBadge success" },
  { fg: "warning-strong", bg: "warning-soft", where: "StatusBadge warning" },
  { fg: "destructive-strong", bg: "destructive-soft", where: "StatusBadge danger" },
  { fg: "info-strong", bg: "info-soft", where: "StatusBadge info" },
  // Alert keeps body text in --foreground and tints only its icon, so
  // this is a different pair from the badges above and needs its own row.
  { fg: "foreground", bg: "success-soft", where: "Alert success body text" },
  { fg: "foreground", bg: "warning-soft", where: "Alert warning body text" },
  { fg: "foreground", bg: "info-soft", where: "Alert info body text" },
  { fg: "foreground", bg: "destructive-soft", where: "Alert danger body text" },
];

// The vivid `--success` / `--warning` / `--info` / `--destructive` hues
// survive as the *dot* colour in `StatusBadge` and the icon tint in
// `Alert`, and they are deliberately NOT asserted at 3:1 here.
//
// WCAG 1.4.11 covers graphics "required to identify user interface
// components and states". These are not: the dot is `aria-hidden` and
// always sits beside a text label, and the Alert icon likewise
// accompanies text. The state is carried by the words, so the dot is
// decoration reinforcing it rather than the indicator itself. Holding
// decoration to 3:1 would have pushed the palette darker for no
// accessibility gain.
//
// This is a judgement call, so it is written down rather than expressed
// as a missing test. What guards the underlying rule is the assertion in
// `components/integrations/integrations-a11y.test.tsx` that a status is
// never colour-only — if the text label were ever dropped, the dot would
// become required and this reasoning would stop holding.

describe.each([
  ["light", LIGHT],
  ["dark", DARK],
])("%s theme", (themeName, theme) => {
  /** 4.5:1, WCAG 1.4.3 — body text. No exemptions. */
  function expectTextAA(fg: string, bg: string): void {
    const ratio = contrast(resolve(theme, fg), resolve(theme, bg));
    expect(ratio, `--${fg} on --${bg} in ${themeName} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      4.5,
    );
  }

  /** 3:1, WCAG 1.4.11 — icons, borders, and other non-text indicators. */
  function expectGraphicAA(fg: string, bg: string): void {
    const ratio = contrast(resolve(theme, fg), resolve(theme, bg));
    expect(ratio, `--${fg} on --${bg} in ${themeName} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      3,
    );
  }
  it("parsed real tokens from globals.css", () => {
    // Guards the parser: an empty map would make every assertion below
    // vacuous, and a silently-passing contrast suite is worse than none.
    expect(Object.keys(theme).length).toBeGreaterThan(20);
    expect(theme["background"]).toMatch(/^#/);
  });

  it.each(TEXT_PAIRS)("$where", ({ fg, bg }) => expectTextAA(fg, bg));

  it.each(STATUS_ON_SOFT)("$where", ({ fg, bg }) => expectTextAA(fg, bg));


  it("the focus ring is distinguishable from the surface it sits on", () => {
    // Checked because §15 forbids suppressing the focus ring, and a ring
    // that meets the letter of that while being invisible against the
    // page meets none of its intent.
    expectGraphicAA("ring", "background");
  });
});
