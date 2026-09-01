"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      // Deliberately generic — the backend never reveals whether the email
      // exists, and the frontend must not either.
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm flex flex-col gap-4"
        aria-labelledby="login-heading"
      >
        <h1 id="login-heading" className="text-2xl font-semibold tracking-tight">
          Log in
        </h1>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <label className="flex flex-col gap-1 text-sm">
          Email
          <input
            required
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Password
          <input
            required
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2"
          />
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-2 rounded bg-foreground text-background px-4 py-2 font-medium disabled:opacity-50"
        >
          {isSubmitting ? "Logging in…" : "Log in"}
        </button>

        <p className="text-sm text-center text-neutral-500">
          Need a workspace?{" "}
          <Link href="/register" className="underline">
            Create one
          </Link>
        </p>
      </form>
    </div>
  );
}
