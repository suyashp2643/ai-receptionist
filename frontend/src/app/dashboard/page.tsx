"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { getOnboardingState, OnboardingState } from "@/lib/phase3-api";
import { summarizeRequirements } from "@/lib/onboarding-progress";

export default function DashboardPage() {
  const { user, memberships, isLoading, logout } = useAuth();
  const router = useRouter();
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null);

  const primaryMembership = memberships[0] as (typeof memberships)[number] | undefined;

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!primaryMembership) return;
    getOnboardingState(primaryMembership.tenant_id)
      .then(setOnboarding)
      .catch(() => setOnboarding(null));
  }, [primaryMembership]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-neutral-500">Loading…</p>
      </div>
    );
  }

  if (!user) {
    // Redirect effect above is in flight; render nothing in the meantime.
    return null;
  }

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-2xl mx-auto flex flex-col gap-8">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Welcome, {user.display_name}</h1>
            {primaryMembership ? (
              <p className="text-neutral-500">
                {primaryMembership.tenant_name}{" "}
                <span className="capitalize">· {primaryMembership.role}</span>
              </p>
            ) : (
              <p className="text-neutral-500">No workspace yet.</p>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="rounded border border-black/15 dark:border-white/20 px-4 py-2 text-sm"
          >
            Log out
          </button>
        </header>

        {primaryMembership && onboarding && onboarding.status !== "completed" && (
          <section className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4">
            <p className="font-medium mb-1">Finish setting up your receptionist</p>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3">
              Your workspace isn&apos;t fully configured yet.
            </p>
            <Link
              href="/onboarding/business"
              className="rounded bg-foreground text-background px-4 py-2 text-sm font-medium"
            >
              Resume setup
            </Link>
          </section>
        )}

        {primaryMembership && onboarding && onboarding.status === "completed" && (
          <section className="rounded-lg border border-black/10 dark:border-white/15 p-4 flex flex-col gap-2">
            <p className="font-medium">Receptionist configuration</p>
            <Link href="/dashboard/settings/business-profile" className="text-sm underline">
              Manage business profile, receptionist, locations, services, knowledge, and more
            </Link>
            <Link href="/dashboard/receptionist/test" className="text-sm underline">
              Open the private test console (mock AI demonstration)
            </Link>
          </section>
        )}

        {primaryMembership &&
          onboarding &&
          (() => {
            const summary = summarizeRequirements(onboarding.status, onboarding.incomplete_requirements);
            if (!summary.isWarning) return null;
            return (
              <section className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 p-4">
                <p className="font-medium mb-1">Configuration needs attention</p>
                <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-2">
                  Your workspace is set up, but something has changed since you completed onboarding:
                </p>
                <ul className="text-sm list-disc list-inside">
                  {summary.requirements.map((r) => (
                    <li key={r.code}>{r.message}</li>
                  ))}
                </ul>
              </section>
            );
          })()}

        <section className="rounded-lg border border-black/10 dark:border-white/15 p-4">
          <h2 className="font-medium mb-2">Your workspaces</h2>
          <ul className="flex flex-col gap-2">
            {memberships.map((membership) => (
              <li
                key={membership.tenant_id}
                className="flex items-center justify-between text-sm border-b border-black/5 dark:border-white/10 pb-2 last:border-0 last:pb-0"
              >
                <span>{membership.tenant_name}</span>
                <span className="capitalize text-neutral-500">{membership.role}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
