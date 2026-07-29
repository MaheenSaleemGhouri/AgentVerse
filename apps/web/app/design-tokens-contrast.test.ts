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
  { fg: "success", bg: "success-soft", where: "StatusBadge success" },
  { fg: "warning", bg: "warning-soft", where: "StatusBadge warning" },
  { fg: "destructive", bg: "destructive-soft", where: "StatusBadge denied / error" },
  { fg: "info", bg: "info-soft", where: "StatusBadge info" },
];

/**
 * Pairs that are rendered today and do NOT meet AA, with the ratio
 * measured when this suite was written.
 *
 * These are real WCAG 2.2 AA failures in the shared AVDS palette, not
 * Phase 6 additions — `StatusBadge`, `Button`, and the knowledge-base
 * count badge all predate it. Fixing them means changing status colours
 * across the whole product, which is a `design-system-architect`
 * decision and not something to slip into an integrations phase.
 *
 * They are pinned rather than skipped. The assertion is that each is
 * still failing *at its known ratio*: if someone darkens a token the
 * test tells them to delete the entry, and if someone makes it worse the
 * test fails. A plain `it.skip` would let the palette drift further
 * while reporting green.
 *
 * Tracked as the blocking item on `CLAUDE.md` §19 gate 7 in
 * `docs/accessibility/phase-6-audit.md`.
 */
const KNOWN_AA_FAILURES: Record<string, Record<string, number>> = {
  light: {
    "primary-foreground/primary": 4.35,
    "destructive-foreground/destructive": 3.76,
    "success/success-soft": 2.52,
    "warning/warning-soft": 2.14,
    "destructive/destructive-soft": 3.29,
    "info/info-soft": 2.82,
  },
  dark: {
    "primary-foreground/primary": 4.35,
    "destructive-foreground/destructive": 3.76,
    // Closest to passing of the lot — the dark soft tints are already
    // much darker than the light ones, which is why success, warning,
    // and info clear AA in this theme and only danger does not.
    "destructive/destructive-soft": 4.37,
  },
};

describe.each([
  ["light", LIGHT],
  ["dark", DARK],
])("%s theme", (themeName, theme) => {
  const known = KNOWN_AA_FAILURES[themeName] ?? {};

  /** AA for body text, unless this pair is a pinned known failure. */
  function expectAA(fg: string, bg: string): void {
    const ratio = contrast(resolve(theme, fg), resolve(theme, bg));
    const pinned = known[`${fg}/${bg}`];
    const detail = `--${fg} on --${bg} in ${themeName} is ${ratio.toFixed(2)}:1`;

    if (pinned === undefined) {
      expect(ratio, detail).toBeGreaterThanOrEqual(4.5);
      return;
    }
    // Still broken, and by the same amount. Either direction of change
    // is a signal worth failing on.
    expect(ratio, `${detail} — pinned at ${pinned}:1. If you fixed it, delete the entry.`).toBeCloseTo(
      pinned,
      1,
    );
    expect(ratio, `${detail} — pinned failures must stay below AA or be un-pinned`).toBeLessThan(4.5);
  }
  it("parsed real tokens from globals.css", () => {
    // Guards the parser: an empty map would make every assertion below
    // vacuous, and a silently-passing contrast suite is worse than none.
    expect(Object.keys(theme).length).toBeGreaterThan(20);
    expect(theme["background"]).toMatch(/^#/);
  });

  it.each(TEXT_PAIRS)("$where", ({ fg, bg }) => expectAA(fg, bg));

  it.each(STATUS_ON_SOFT)("$where", ({ fg, bg }) => expectAA(fg, bg));

  it("the focus ring is distinguishable from the surface it sits on (3:1, WCAG 1.4.11)", () => {
    // A non-text UI indicator, so 3:1 rather than 4.5:1. Checked because
    // §15 forbids suppressing the focus ring, and a ring that meets the
    // letter of that while being invisible against the page meets none
    // of its intent.
    const ratio = contrast(resolve(theme, "ring"), resolve(theme, "background"));
    expect(ratio, `--ring on --background in ${themeName} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(3);
  });
});
