/**
 * Docs search — pure, and deliberately client-side.
 *
 * The corpus is a few dozen public guides that are identical for every
 * reader, so the whole index ships with the page and matching happens in
 * the browser. An API round trip per keystroke would buy nothing: there
 * is nothing tenant-specific to scope, nothing to authorize, and the
 * index is smaller than the request would be.
 *
 * That is the opposite of the workspace search in `lib/api/search.ts`,
 * which must go to the server precisely because its results *are*
 * tenant-scoped. Two different problems, two different answers.
 */

export interface DocsSearchEntry {
  readonly slug: string;
  readonly title: string;
  readonly summary: string;
  readonly pillar: string;
  readonly pillarName: string;
  /** Section headings, so a query matches a guide by what is *in* it. */
  readonly headings: readonly string[];
}

/** Ranked highest first. Field weights, so a title match beats a
 * heading match beats a summary match — a reader searching "webhook"
 * wants the webhooks guide, not the guide that mentions webhooks once. */
const TITLE_WEIGHT = 8;
const HEADING_WEIGHT = 3;
const SUMMARY_WEIGHT = 2;
const PILLAR_WEIGHT = 1;

export function searchDocs(
  index: readonly DocsSearchEntry[],
  query: string,
  limit = 6,
): readonly DocsSearchEntry[] {
  const terms = query
    .toLowerCase()
    .split(/\s+/)
    .filter((term) => term.length > 0);
  if (terms.length === 0) return [];

  const scored = index
    .map((entry) => ({ entry, score: scoreEntry(entry, terms) }))
    // Every term must hit something. Without this, "billing webhook"
    // would return every billing guide — the second word would be doing
    // no work, which is not what someone typing two words expects.
    .filter((candidate) => candidate.score > 0);

  scored.sort(
    (left, right) => right.score - left.score || left.entry.title.localeCompare(right.entry.title),
  );
  return scored.slice(0, limit).map((candidate) => candidate.entry);
}

function scoreEntry(entry: DocsSearchEntry, terms: readonly string[]): number {
  let total = 0;

  for (const term of terms) {
    let termScore = 0;
    if (entry.title.toLowerCase().includes(term)) termScore += TITLE_WEIGHT;
    if (entry.headings.some((heading) => heading.toLowerCase().includes(term))) {
      termScore += HEADING_WEIGHT;
    }
    if (entry.summary.toLowerCase().includes(term)) termScore += SUMMARY_WEIGHT;
    if (entry.pillarName.toLowerCase().includes(term)) termScore += PILLAR_WEIGHT;

    // One unmatched term disqualifies the entry outright.
    if (termScore === 0) return 0;
    total += termScore;
  }

  return total;
}
