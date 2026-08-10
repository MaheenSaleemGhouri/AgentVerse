/**
 * The auth route group's own frame.
 *
 * Themed like every other surface in the product — `bg-background`, not
 * a hardcoded dark hex. The previous version opted the whole auth flow
 * out of the light/dark switch to serve a fixed cyberpunk scene; once
 * that scene is gone (see `components/auth/auth-hero.tsx`), there is no
 * reason for auth to be the one surface that ignores the theme provider
 * every other route already sits inside (`app/providers.tsx`).
 */

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return <main className="min-h-screen bg-background">{children}</main>;
}
