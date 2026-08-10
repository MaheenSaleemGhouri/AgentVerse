"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Building2, Lock, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthLockup } from "@/components/auth/auth-lockup";
import { AuthSubmitButton, OrDivider, SocialButton } from "@/components/auth/auth-buttons";
import { AuthField } from "@/components/auth/auth-field";
import { AuthPanel } from "@/components/auth/auth-panel";
import { Checkbox } from "@/components/ui/checkbox";
import { authClient } from "@/lib/auth-client";
import type { SocialProvider } from "@/lib/social-providers";
import type { SsoLoginOption } from "@/lib/sso-login-options";

/** Colocated with its inferred type so validation and typing cannot
 *  drift (§6, forms). */
const loginSchema = z.object({
  // Trimmed before the format check — a stray leading/trailing space
  // (autocomplete, mobile keyboards) would otherwise fail `.email()`
  // silently with no visual cue the space is even there.
  email: z.string().trim().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
  rememberMe: z.boolean(),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginForm({
  socialProviders,
  ssoOptions = [],
}: {
  socialProviders: SocialProvider[];
  ssoOptions?: SsoLoginOption[];
}): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);
  const [socialPending, setSocialPending] = useState(false);
  const [ssoPending, setSsoPending] = useState(false);

  const redirectTo = searchParams.get("redirect") ?? "/dashboard";

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "", rememberMe: true },
  });

  async function onSubmit(values: LoginValues): Promise<void> {
    setFormError(null);
    const { error } = await authClient.signIn.email({
      email: values.email,
      password: values.password,
      rememberMe: values.rememberMe,
    });

    if (error) {
      // Better Auth returns a uniform failure for bad email and bad
      // password alike, and it is left that way: distinguishing them
      // tells an attacker which addresses have accounts (§10, uniform
      // auth errors).
      setFormError(error.message ?? "Invalid email or password.");
      return;
    }
    router.push(redirectTo);
  }

  async function handleSso(option: SsoLoginOption): Promise<void> {
    setSsoPending(true);
    setFormError(null);
    if (option.protocol === "saml") {
      // SAML is a plain browser redirect into our own SP route, not a
      // Better Auth client call — the flow is a POST-back from the IdP,
      // which the plugin layer has no part in.
      window.location.href = `/api/sso/saml/${option.providerId}/login`;
      return;
    }
    const { error } = await authClient.signIn.oauth2({
      providerId: option.providerId,
      callbackURL: redirectTo,
    });
    if (error) {
      setSsoPending(false);
      setFormError(error.message ?? "Could not start single sign-on.");
    }
  }

  async function handleSocial(provider: SocialProvider): Promise<void> {
    setSocialPending(true);
    setFormError(null);
    const { error } = await authClient.signIn.social({ provider, callbackURL: redirectTo });
    if (error) {
      setSocialPending(false);
      setFormError(error.message ?? `Could not continue with ${provider}.`);
    }
  }

  return (
    <AuthPanel elevated>
      <AuthLockup className="mb-6" />

      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        Welcome back{" "}
        <span role="img" aria-label="waving hand">
          👋
        </span>
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">Log in to your account</p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
        <AuthField
          label="Email"
          icon={Mail}
          type="email"
          autoComplete="email"
          placeholder="Enter your email"
          error={errors.email?.message}
          {...register("email")}
        />

        <AuthField
          label="Password"
          icon={Lock}
          revealable
          autoComplete="current-password"
          placeholder="Enter your password"
          error={errors.password?.message}
          {...register("password")}
        />

        <div className="flex items-center justify-between">
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-foreground">
            <Checkbox
              checked={watch("rememberMe")}
              onCheckedChange={(checked) => setValue("rememberMe", checked === true)}
            />
            Remember me
          </label>
          <Link
            href="/forgot-password"
            className="rounded text-[13px] font-medium text-primary transition-colors hover:underline focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            Forgot password?
          </Link>
        </div>

        <AnimatePresence mode="wait">
          {formError && (
            <motion.p
              key={formError}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive-soft px-3 py-2 text-xs text-destructive-strong"
            >
              {formError}
            </motion.p>
          )}
        </AnimatePresence>

        <AuthSubmitButton icon={ArrowRight} pending={isSubmitting} pendingLabel="Logging in…" className="mt-1">
          Login
        </AuthSubmitButton>
      </form>

      {(socialProviders.length > 0 || ssoOptions.length > 0) && (
        <div className="mt-5 flex flex-col gap-3">
          <OrDivider />
          {socialProviders.map((provider) => (
            <SocialButton
              key={provider}
              provider={provider}
              disabled={socialPending || ssoPending || isSubmitting}
              onClick={() => void handleSocial(provider)}
            />
          ))}
          {/* Rendered only when an organization actually has an enabled
              SSO config, so this is never a button that fails on click —
              the same rule the social buttons follow. */}
          {ssoOptions.map((option) => (
            <button
              key={option.providerId}
              type="button"
              disabled={socialPending || ssoPending || isSubmitting}
              onClick={() => void handleSso(option)}
              className="flex w-full items-center justify-center gap-2.5 rounded-md border border-input bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
            >
              <Building2 className="size-4" aria-hidden="true" />
              {ssoPending ? "Redirecting…" : "Continue with single sign-on"}
            </button>
          ))}
        </div>
      )}

      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link
          href="/signup"
          className="rounded font-medium text-primary transition-colors hover:underline focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          Sign up
        </Link>
      </p>
    </AuthPanel>
  );
}
