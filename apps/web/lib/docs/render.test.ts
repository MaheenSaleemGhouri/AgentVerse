/**
 * Heading extraction and slugging.
 *
 * These two are pinned together because the on-page contents links to
 * `#id` while `rehype-slug` writes the `id` onto the rendered heading —
 * two separate implementations, one over markdown source and one over
 * HTML. If they disagree, every anchor in the contents list silently
 * goes nowhere, which is the sort of breakage nobody notices in review.
 */

import { describe, expect, it } from "vitest";

import { extractHeadings, slugifyHeading } from "./render";

describe("extractHeadings", () => {
  it("takes h2 and h3", () => {
    const headings = extractHeadings("## Prerequisites\n\n### Install\n");
    expect(headings).toEqual([
      { id: "prerequisites", text: "Prerequisites", level: 2 },
      { id: "install", text: "Install", level: 3 },
    ]);
  });

  it("ignores h1", () => {
    // The page title comes from frontmatter, not the body, so an `h1`
    // in a guide would duplicate it.
    expect(extractHeadings("# Title\n\n## Real heading\n")).toHaveLength(1);
  });

  it("ignores headings deeper than h3", () => {
    expect(extractHeadings("#### Too deep\n")).toEqual([]);
  });

  it("ignores comments inside fenced code blocks", () => {
    // The bug this exists to prevent: a shell sample whose first line is
    // `# install the CLI` becoming a phantom entry in the contents.
    const markdown = ["## Setup", "", "```bash", "# install the CLI", "npm i -g x", "```", ""].join(
      "\n",
    );
    expect(extractHeadings(markdown).map((heading) => heading.text)).toEqual(["Setup"]);
  });

  it("strips backticks from heading text", () => {
    const [heading] = extractHeadings("## The `run` command\n");
    expect(heading?.text).toBe("The run command");
  });

  it("returns nothing for a guide with no headings", () => {
    expect(extractHeadings("Just a paragraph.\n")).toEqual([]);
  });
});

describe("slugifyHeading", () => {
  it("lowercases and hyphenates", () => {
    expect(slugifyHeading("Verify the signature")).toBe("verify-the-signature");
  });

  it("drops punctuation", () => {
    expect(slugifyHeading("Retries, and idempotency!")).toBe("retries-and-idempotency");
  });

  it("collapses runs of whitespace", () => {
    expect(slugifyHeading("Runs   are    asynchronous")).toBe("runs-are-asynchronous");
  });

  it("keeps digits", () => {
    expect(slugifyHeading("Step 2 of 3")).toBe("step-2-of-3");
  });

  it("trims", () => {
    expect(slugifyHeading("  Events  ")).toBe("events");
  });
});
