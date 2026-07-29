"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Lock, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AgentVerseLockup } from "@/components/auth/agentverse-mark";
import { GradientButton, OrDivider, SocialButton } from "@/components/auth/auth-buttons";
import { AuthField } from "@/components/auth/auth-field";
import { GlassPanel } from "@/components/auth/glass-panel";
import { Checkbox } from "@/components/ui/checkbox";
import { authClient } from "@/lib/auth-client";
import type { SocialProvider } from "@/lib/social-providers";

/** Colocated with its inferred type so validation and typing cannot
 *  drift (§6, forms). */
const loginSchema = z.object({
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
  rememberMe: z.boolean(),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginForm({
  socialProviders,
}: {
  socialProviders: SocialProvider[];
}): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);
  const [socialPending, setSocialPending] = useState(false);

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
    <GlassPanel tilt="left">
      <AgentVerseLockup className="mb-6" />

      <h1 className="text-2xl font-semibold tracking-tight text-white">
        Welcome Back!{" "}
        <span role="img" aria-label="waving hand">
          👋
        </span>
      </h1>
      <p className="mt-1 text-sm text-[#a8a2c8]">Login to your account</p>

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
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-[#cfcae8]">
            <Checkbox
              checked={watch("rememberMe")}
              onCheckedChange={(checked) => setValue("rememberMe", checked === true)}
              className="border-white/20 data-[state=checked]:border-[#a855f7] data-[state=checked]:bg-[#a855f7]"
            />
            Remember me
          </label>
          <Link
            href="/forgot-password"
            className="rounded text-[13px] font-medium text-[#c084fc] transition-colors hover:text-[#d8b4fe] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40"
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
              className="rounded-lg border border-[#f4655b]/30 bg-[#f4655b]/10 px-3 py-2 text-xs text-[#f4655b]"
            >
              {formError}
            </motion.p>
          )}
        </AnimatePresence>

        <GradientButton
          type="submit"
          icon={ArrowRight}
          pending={isSubmitting}
          pendingLabel="Logging in…"
          className="mt-1"
        >
          Login
        </GradientButton>
      </form>

      {socialProviders.length > 0 && (
        <div className="mt-5 flex flex-col gap-3">
          <OrDivider />
          {socialProviders.map((provider) => (
            <SocialButton
              key={provider}
              provider={provider}
              disabled={socialPending || isSubmitting}
              onClick={() => void handleSocial(provider)}
            />
          ))}
        </div>
      )}

      <p className="mt-6 text-center text-[13px] text-[#a8a2c8]">
        Don&apos;t have an account?{" "}
        <Link
          href="/signup"
          className="rounded font-medium text-[#c084fc] transition-colors hover:text-[#d8b4fe] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40"
        >
          Sign up
        </Link>
      </p>
    </GlassPanel>
  );
}
