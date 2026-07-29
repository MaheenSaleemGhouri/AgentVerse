"use client";

/**
 * The three-column composition: login, hero, signup.
 *
 * The approved design shows both panels on one screen, but `/login` and
 * `/signup` are separate routes and must stay that way — they are
 * linkable, bookmarkable, and already referenced by redirects elsewhere
 * in the app. So both routes render this shell and pass which panel is
 * `active`.
 *
 * On desktop that is invisible: both panels are present, exactly as
 * designed. Below `lg` there is no room for three columns, so only the
 * active panel renders — a phone showing a signup form the user did not
 * ask for would be worse than the design being narrower there.
 */

import { Suspense } from "react";

import { LoginForm } from "@/app/(auth)/login/login-form";
import { SignupForm } from "@/app/(auth)/signup/signup-form";
import type { SocialProvider } from "@/lib/social-providers";

import { AuthHero } from "./auth-hero";
import { BuiltOnStrip, TrustBar } from "./trust-sections";

export function AuthShell({
  active,
  socialProviders,
}: {
  active: "login" | "signup";
  socialProviders: SocialProvider[];
}): React.JSX.Element {
  return (
    <div className="relative mx-auto flex w-full max-w-[1600px] flex-col gap-10 px-4 py-10 sm:px-6 lg:px-8">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(320px,380px)_minmax(0,1fr)_minmax(320px,380px)] lg:gap-6 xl:gap-10">
        {/* Login. Hidden below lg when signup is the active route. */}
        <div className={active === "login" ? "order-1" : "order-1 hidden lg:block"}>
          {/* LoginForm reads `?redirect=` via useSearchParams, which
              needs a Suspense boundary for this page to prerender. */}
          <Suspense fallback={<PanelSkeleton />}>
            <LoginForm socialProviders={socialProviders} />
          </Suspense>
        </div>

        {/* Hero. Ordered last on small screens so the form a user came
            for is the first thing they reach, not 500px of scene. */}
        <div className="order-3 lg:order-2">
          <AuthHero />
        </div>

        <div className={active === "signup" ? "order-2 lg:order-3" : "order-2 hidden lg:order-3 lg:block"}>
          <SignupForm socialProviders={socialProviders} />
        </div>
      </div>

      <div className="order-4 flex flex-col gap-4">
        <BuiltOnStrip />
        <TrustBar />
      </div>
    </div>
  );
}

function PanelSkeleton(): React.JSX.Element {
  // Matches the panel's height so the Suspense swap does not shift the
  // grid — the layout-stability requirement in §6.
  return (
    <div
      aria-hidden="true"
      className="h-[560px] w-full animate-pulse rounded-3xl border border-white/10 bg-white/[0.03]"
    />
  );
}
