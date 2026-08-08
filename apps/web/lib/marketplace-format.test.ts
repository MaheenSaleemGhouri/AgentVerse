/**
 * Price formatting.
 *
 * The only place cents become dollars, so this is the only place a
 * rounding or division mistake could turn into a wrong price on a public
 * page (Rule 15: money is integer cents everywhere else).
 */

import { describe, expect, it } from "vitest";

import { formatPriceCents } from "./marketplace-format";

describe("formatPriceCents", () => {
  it("drops the decimals on a whole-dollar price", () => {
    expect(formatPriceCents(2900)).toBe("$29");
  });

  it("keeps both digits when there are cents", () => {
    expect(formatPriceCents(2999)).toBe("$29.99");
  });

  it("keeps a trailing zero rather than showing one decimal", () => {
    expect(formatPriceCents(2950)).toBe("$29.50");
  });

  it("handles a price under a dollar", () => {
    expect(formatPriceCents(99)).toBe("$0.99");
  });

  it("formats zero as free-of-charge dollars, not an empty string", () => {
    // Zero-priced listings render "Free" in the UI, but the formatter
    // must still return something sane if it is ever called with 0.
    expect(formatPriceCents(0)).toBe("$0");
  });

  it("groups thousands", () => {
    expect(formatPriceCents(199_900)).toBe("$1,999");
  });
});
