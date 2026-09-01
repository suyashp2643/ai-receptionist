"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function DashboardPage() {
  const { user, memberships, isLoading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

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

  const primaryMembership = memberships[0] as (typeof memberships)[number] | undefined;

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
