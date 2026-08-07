import type { Metadata } from "next";
import { Geist, Geist_Mono, JetBrains_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

/**
 * A third font, not a replacement for `Geist_Mono`.
 *
 * Repointing `--font-geist-mono` at JetBrains Mono would restyle every
 * run id, trace timestamp, log line and token count in the product —
 * a redesign of pages this milestone is explicitly not allowed to
 * touch. So this variable exists alongside it and is applied only to
 * documentation code blocks (see `.docs-prose` in `globals.css`), which
 * are a new surface with no existing look to preserve.
 */
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
        className={`${geistSans.variable} ${geistMono.variable} ${jetbrainsMono.variable} bg-background text-foreground antialiased`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
