/**
 * The auth route group's own frame.
 *
 * Dark-only and self-contained: this is the one surface in the product
 * that is a composed cinematic scene rather than a themed application
 * page, so it opts out of the light/dark switch instead of trying to
 * work in both. The dashboard is unaffected — the theme provider still
 * governs everything under `(dashboard)`.
 *
 * `overflow-x-hidden` rather than letting the glow bleed: the panel
 * tilts and the radial gradients extend past the viewport by design, and
 * without this they would produce a horizontal scrollbar, which the
 * brief rules out explicitly.
 */

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#08061a] text-white antialiased">
      {/* Ambient depth behind everything, including the 3D canvas, so
          the page still reads as composed while the scene loads. */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,rgba(76,29,149,0.45),transparent_60%),radial-gradient(ellipse_60%_50%_at_50%_100%,rgba(14,116,144,0.22),transparent_60%)]"
      />
      {/* Fine grid, barely visible — the texture that keeps a large dark
          area from reading as flat. */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 opacity-[0.05] [background-image:linear-gradient(rgba(168,85,247,0.6)_1px,transparent_1px),linear-gradient(90deg,rgba(168,85,247,0.6)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_40%,black,transparent)]"
      />
      <main className="relative">{children}</main>
    </div>
  );
}
