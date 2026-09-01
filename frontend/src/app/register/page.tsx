"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";
import { resolveDefaultTimezone, useTimezoneOptions } from "@/lib/timezones";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { timezones, isLoading: timezonesLoading } = useTimezoneOptions();

  // Auto-select the browser's detected timezone (normalized if it's a known
  // legacy alias, e.g. Asia/Calcutta -> Asia/Kolkata) exactly once, as soon
  // as the backend-valid list has loaded — never before, since we can't
  // confirm the detected zone is actually acceptable until then. Guarded by
  // a ref rather than depending on `timezones` so this can't re-fire and
  // clobber a value the user has since picked themselves.
  const hasSetDefaultTimezone = useRef(false);
  useEffect(() => {
    if (!timezonesLoading && !hasSetDefaultTimezone.current) {
      hasSetDefaultTimezone.current = true;
      setTimezone(resolveDefaultTimezone(timezones));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timezonesLoading]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await register({
        display_name: displayName,
        email,
        password,
        workspace_name: workspaceName,
        timezone,
      });
      router.push("/dashboard");
    } catch (err) {
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
        aria-labelledby="register-heading"
      >
        <h1 id="register-heading" className="text-2xl font-semibold tracking-tight">
          Create your workspace
        </h1>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <label className="flex flex-col gap-1 text-sm">
          Name
          <input
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoComplete="name"
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2"
          />
        </label>

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
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            aria-describedby="password-hint"
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2"
          />
          <span id="password-hint" className="text-xs text-neutral-500">
            At least 8 characters.
          </span>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Workspace name
          <input
            required
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Time zone
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2"
          >
            {timezones.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-2 rounded bg-foreground text-background px-4 py-2 font-medium disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create workspace"}
        </button>

        <p className="text-sm text-center text-neutral-500">
          Already have an account?{" "}
          <Link href="/login" className="underline">
            Log in
          </Link>
        </p>
      </form>
    </div>
  );
}
