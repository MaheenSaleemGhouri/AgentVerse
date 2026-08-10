"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { Lock, Mail, User, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthLockup } from "@/components/auth/auth-lockup";
import { AuthSubmitButton, OrDivider, SocialButton } from "@/components/auth/auth-buttons";
import { AuthField } from "@/components/auth/auth-field";
import { AuthPanel } from "@/components/auth/auth-panel";
import { PasswordRequirements, satisfiesAllRules } from "@/components/auth/password-requirements";
import { authClient } from "@/lib/auth-client";
import type { SocialProvider } from "@/lib/social-providers";

const signupSchema = z
  .object({
    name: z.string().min(1, "Name is required.").max(80, "Name is too long."),
    // Trimmed before the format check — a stray leading/trailing space
    // (autocomplete, mobile keyboards) would otherwise fail `.email()`
    // silently with no visual cue the space is even there.
    email: z.string().trim().min(1, "Email is required.").email("Enter a valid email address."),
    // The rule list is the source; this refinement reads it rather than
    // restating it, so the checklist and the validator cannot disagree
    // (Rule 3).
    password: z.string().refine(satisfiesAllRules, "Password does not meet all requirements."),
    confirmPassword: z.string().min(1, "Confirm your password."),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });
type SignupValues = z.infer<typeof signupSchema>;

export function SignupForm({
  socialProviders,
}: {
  socialProviders: SocialProvider[];
}): React.JSX.Element {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const [socialPending, setSocialPending] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    // Validates as the user types *after* the first blur, so the
    // checklist and the field errors agree instead of the list ticking
    // green while an untouched field still shows nothing.
    mode: "onTouched",
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
  });

  const password = watch("password");

  async function onSubmit(values: SignupValues): Promise<void> {
    setFormError(null);
    const { error } = await authClient.signUp.email({
      name: values.name,
      email: values.email,
      password: values.password,
    });

    if (error) {
      setFormError(error.message ?? "Could not create your account.");
      return;
    }
    router.push("/dashboard");
  }

  async function handleSocial(provider: SocialProvider): Promise<void> {
    setSocialPending(true);
    setFormError(null);
    const { error } = await authClient.signIn.social({ provider, callbackURL: "/dashboard" });
    if (error) {
      setSocialPending(false);
      setFormError(error.message ?? `Could not continue with ${provider}.`);
    }
  }

  return (
    <AuthPanel elevated>
      <AuthLockup className="mb-6" />

      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        Create your account{" "}
        <span role="img" aria-label="rocket">
          🚀
        </span>
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">Start your AI journey today</p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
        <AuthField
          label="Full name"
          icon={User}
          autoComplete="name"
          placeholder="Enter your full name"
          error={errors.name?.message}
          {...register("name")}
        />

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
          autoComplete="new-password"
          placeholder="Create a password"
          // The checklist below already names exactly what is missing, so
          // repeating "does not meet all requirements" under the field
          // would be the same information twice.
          error={errors.password && password.length === 0 ? errors.password.message : undefined}
          {...register("password")}
        />

        <AuthField
          label="Confirm password"
          icon={Lock}
          revealable
          autoComplete="new-password"
          placeholder="Confirm your password"
          error={errors.confirmPassword?.message}
          {...register("confirmPassword")}
        />

        <PasswordRequirements value={password} />

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

        <AuthSubmitButton icon={UserPlus} pending={isSubmitting} pendingLabel="Creating account…" className="mt-1">
          Create account
        </AuthSubmitButton>
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

      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        Already have an account?{" "}
        <Link
          href="/login"
          className="rounded font-medium text-primary transition-colors hover:underline focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          Login
        </Link>
      </p>
    </AuthPanel>
  );
}
