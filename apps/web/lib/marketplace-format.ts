/**
 * Money formatting for the catalog.
 *
 * Prices arrive as integer cents (Rule 15) and are divided exactly once,
 * here. Every other formatting of a price in the product goes through
 * this function, so a `/100` cannot appear in two components and
 * disagree — and nothing ever does arithmetic on a float price.
 */
export function formatPriceCents(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    // Whole-dollar prices read as "$29", not "$29.00"; anything with
    // cents keeps both digits.
    minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}
