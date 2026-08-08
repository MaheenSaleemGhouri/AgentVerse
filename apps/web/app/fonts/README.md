# Self-hosted fonts

## Satoshi

The heading typeface locked by
[`docs/design/design-system.md`](../../../../docs/design/design-system.md) §3.

**Why these files are committed rather than fetched:** Satoshi is not on
Google Fonts, so `next/font/google` cannot supply it. The alternative —
linking Fontshare's stylesheet at runtime — adds a render-blocking
request to a third-party host on every page load and reintroduces the
layout shift `next/font` exists to remove. Self-hosting through
`next/font/local` gives a preloaded, self-referencing `@font-face` with
a size-adjusted fallback and no external request.

**Weights:** 400 (Regular), 500 (Medium), 700 (Bold). The reference
specifies Satoshi Bold 48px for a hero heading and Satoshi Medium 24px
for a section title; 400 covers lighter display use. Three weights is
~76 KB total — additional weights are not carried until a surface needs
one.

**Source:** [Fontshare](https://www.fontshare.com/fonts/satoshi), by the
Indian Type Foundry. Retrieved from `api.fontshare.com` /
`cdn.fontshare.com` on 2026-08-08.

**Licence:** the [Fontshare Free Font
Licence](https://www.fontshare.com/licenses/itf-ffl) — free for personal
and commercial use, including web embedding of the provided webfont
files. The files here are unmodified as retrieved. Do not re-export,
subset, or rename them without re-checking the licence terms.

Geist, Geist Mono and JetBrains Mono remain on `next/font/google` and
need no files here.
