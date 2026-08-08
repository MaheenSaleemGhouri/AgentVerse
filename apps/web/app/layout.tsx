import type { Metadata } from "next";
import { Geist, Geist_Mono, JetBrains_Mono } from "next/font/google";
import localFont from "next/font/local";
import { Providers } from "./providers";
import "./globals.css";

/**
 * The three locked typefaces (docs/design/design-system.md §3):
 * Satoshi for headings, Geist for UI and body, JetBrains Mono for code.
 *
 * All three are loaded through `next/font`, so each is self-hosted,
 * preloaded, and given a size-adjusted fallback — no external request
 * and no layout shift when the real face arrives.
 */

/**
 * Satoshi is not on Google Fonts, so it is self-hosted from
 * `app/fonts/` — see the README there for provenance and licence.
 *
 * `adjustFontFallback` is left at its default so Next.js synthesises a
 * metrics-matched local fallback: with three separate weight files and
 * `display: swap`, an unmatched fallback is exactly where a visible
 * reflow would come from.
 */
const satoshi = localFont({
  variable: "--font-satoshi",
  display: "swap",
  src: [
    { path: "./fonts/Satoshi-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/Satoshi-Medium.woff2", weight: "500", style: "normal" },
    { path: "./fonts/Satoshi-Bold.woff2", weight: "700", style: "normal" },
  ],
});

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

/**
 * Kept as the fallback inside `--font-mono` rather than removed.
 * JetBrains Mono is now the product's mono face, but Geist Mono is
 * already loaded and its metrics are close enough that it covers the
 * swap window invisibly.
 */
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AgentVerse",
  description:
    "AgentVerse — build, deploy, and orchestrate AI agents and multi-agent systems.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${satoshi.variable} ${geistSans.variable} ${geistMono.variable} ${jetbrainsMono.variable} bg-background text-foreground antialiased`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
