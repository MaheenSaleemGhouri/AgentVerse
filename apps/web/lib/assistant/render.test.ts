import { describe, expect, it } from "vitest";

import { parseAnswer, parseInlines } from "@/lib/assistant/render";

describe("the assistant answer renderer", () => {
  it("keeps documentation citations as links", () => {
    expect(parseInlines("See [the guide](/docs/platform/webhooks#signing) for more.")).toEqual([
      { text: "See " },
      { text: "the guide", href: "/docs/platform/webhooks#signing" },
      { text: " for more." },
    ]);
  });

  it("renders a non-docs URL as literal text rather than a link", () => {
    // The model was given only /docs paths. Anything else it produces is
    // invented, and an invented link is worse than no link.
    expect(parseInlines("[click](https://example.invalid/phish)")).toEqual([
      { text: "[click](https://example.invalid/phish)" },
    ]);
  });

  it("refuses a javascript: payload", () => {
    const [only] = parseInlines("[safe](javascript:alert(1))");
    expect(only?.href).toBeUndefined();
  });

  it("separates paragraphs and bullets", () => {
    expect(parseAnswer("Open settings.\n\n- One\n- Two")).toEqual([
      { kind: "paragraph", inlines: [{ text: "Open settings." }] },
      { kind: "bullet", inlines: [{ text: "One" }] },
      { kind: "bullet", inlines: [{ text: "Two" }] },
    ]);
  });

  it("leaves unsupported markdown as the characters it is", () => {
    // Boring failure mode on purpose: a stray backtick is a backtick,
    // never a half-parsed fragment.
    expect(parseAnswer("**bold** and `code`")).toEqual([
      { kind: "paragraph", inlines: [{ text: "**bold** and `code`" }] },
    ]);
  });

  it("handles a partial stream without throwing", () => {
    // Every intermediate prefix of a streamed answer is rendered, so an
    // unterminated link must not break mid-token.
    expect(() => parseAnswer("See [the gui")).not.toThrow();
    expect(parseAnswer("See [the gui")).toEqual([
      { kind: "paragraph", inlines: [{ text: "See [the gui" }] },
    ]);
  });

  it("is not confused by a second call (no shared regex state)", () => {
    const line = "[a](/docs/x) and [b](/docs/y)";
    expect(parseInlines(line)).toEqual(parseInlines(line));
  });
});
