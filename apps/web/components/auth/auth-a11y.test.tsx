/**
 * WCAG 2.2 AA regression gate for the rebuilt auth surfaces (CLAUDE.md
 * §15, Rule 7 — accessibility is a merge gate, not a follow-up).
 *
 * Mirrors `components/integrations/integrations-a11y.test.tsx`: axe-core
 * runs against each panel's real rendered markup, not a simplified
 * stand-in. What it deliberately does NOT claim: axe catches a minority
 * of real accessibility problems — focus order, live-region verbosity,
 * and whether the keyboard/screen-reader flow is actually usable still
 * need a manual pass, which has not been run against these surfaces yet.
 *
 * Colour contrast is disabled for the same reason as the integrations
 * suite: jsdom computes no layout or colour, so axe's contrast rule
 * would report a pass that means nothing.
 *
 * The 3D scene is not rendered here. `SceneLoader` gates the canvas on
 * `window.matchMedia` / WebGL, none of which jsdom implements, so it
 * always resolves to `SceneFallback` — which is exactly the DOM real
 * users without WebGL or with reduced motion get, and the canvas itself
 * is `aria-hidden` in the surfaces that do mount it, so it contributes
 * nothing to the accessibility tree either way.
 */

import { cleanup, render } from "@testing-library/react";
import axe from "axe-core";
import * as React from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

beforeAll(() => {
  // Radix (Checkbox) measures via ResizeObserver; jsdom has none.
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
  // The trust strips use framer-motion's `whileInView`, which mounts an
  // IntersectionObserver — also absent from jsdom. Without this shim the
  // component throws during a layout effect rather than failing an axe
  // rule, which is a worse failure mode to debug.
  globalThis.IntersectionObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  } as unknown as typeof IntersectionObserver;
  globalThis.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof globalThis.matchMedia;
});

// authClient is mocked rather than pointed at a real server: this suite
// asserts markup and ARIA wiring, not network behaviour — the same
// division the integrations suite draws around its query hooks.
vi.mock("@/lib/auth-client", () => ({
  authClient: {
    signIn: {
      email: vi.fn().mockResolvedValue({ error: null }),
      social: vi.fn().mockResolvedValue({ error: null }),
    },
    signUp: {
      email: vi.fn().mockResolvedValue({ error: null }),
    },
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const { LoginForm } = await import("@/app/(auth)/login/login-form");
const { SignupForm } = await import("@/app/(auth)/signup/signup-form");
const { AuthHero } = await import("@/components/auth/auth-hero");
const { BuiltOnStrip, TrustBar } = await import("@/components/auth/trust-sections");
const ForgotPasswordPage = (await import("@/app/(auth)/forgot-password/page")).default;

const SOCIAL_PROVIDERS = ["google", "github"] as const;

/** Mirrors the integrations suite's helper — same rule set, same reason
 *  for disabling colour-contrast (see file header). */
async function violationsIn(container: HTMLElement): Promise<axe.Result[]> {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations;
}

function describeViolations(violations: axe.Result[]): string {
  return violations
    .map((v) => `${v.id} (${v.impact}): ${v.help}\n    ${v.nodes.map((n) => n.html).join("\n    ")}`)
    .join("\n");
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Auth surfaces — axe", () => {
  it("login panel has no violations, with and without social providers", async () => {
    const withSocial = render(<LoginForm socialProviders={[...SOCIAL_PROVIDERS]} />);
    expect(describeViolations(await violationsIn(withSocial.container))).toBe("");
    withSocial.unmount();

    const withoutSocial = render(<LoginForm socialProviders={[]} />);
    expect(describeViolations(await violationsIn(withoutSocial.container))).toBe("");
  });

  it(
    "signup panel has no violations, including the live password checklist",
    async () => {
      const { container, getByLabelText } = render(
        <SignupForm socialProviders={[...SOCIAL_PROVIDERS]} />
      );

      // The checklist re-renders on every keystroke (aria-live="polite") —
      // exercised rather than left at its empty initial state, since a
      // dynamically-updated region is exactly where a stale aria-live
      // wiring would surface.
      const { fireEvent } = await import("@testing-library/react");
      fireEvent.change(getByLabelText("Password"), { target: { value: "Weak1" } });

      expect(describeViolations(await violationsIn(container))).toBe("");
    },
    // This form's mount cost (react-hook-form + zod resolver + framer-motion
    // + axe.run against the full rendered tree) occasionally exceeds
    // vitest's 5s default on this WSL-hosted volume — the same slow-import
    // filesystem behaviour documented in vitest.config.ts, not a hang.
    // Raised per-test rather than globally so an actual hang elsewhere
    // still fails fast.
    15_000
  );

  it("the hero column (mark, heading, capability cards, scene fallback) has no violations", async () => {
    const { container } = render(<AuthHero />);
    expect(describeViolations(await violationsIn(container))).toBe("");
  });

  it("the built-on and trust strips have no violations", async () => {
    const { container } = render(
      <>
        <BuiltOnStrip />
        <TrustBar />
      </>,
    );
    expect(describeViolations(await violationsIn(container))).toBe("");
  });

  it("the forgot-password page has no violations", async () => {
    const { container } = render(<ForgotPasswordPage />);
    expect(describeViolations(await violationsIn(container))).toBe("");
  });
});
