"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

const NAV = [
  { href: "/dashboard/settings/business-profile", label: "Business profile" },
  { href: "/dashboard/settings/receptionist", label: "Receptionist" },
  { href: "/dashboard/settings/locations", label: "Locations" },
  { href: "/dashboard/settings/services", label: "Services" },
  { href: "/dashboard/settings/knowledge", label: "Knowledge & FAQs" },
  { href: "/dashboard/settings/qualification", label: "Qualification" },
  { href: "/dashboard/settings/actions", label: "Actions" },
];

export function SettingsShell({
  title,
  children,
}: {
  title: string;
  children: (ctx: { tenantId: string; canEdit: boolean }) => ReactNode;
}) {
  const { user, memberships, isLoading } = useAuth();
  const router = useRouter();
  const membership = memberships[0];

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-neutral-500">Loading…</p>
      </div>
    );
  }
  if (!user || !membership) return null;

  const canEdit = membership.role === "owner" || membership.role === "admin";

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto flex flex-col md:flex-row gap-8">
        <nav className="flex md:flex-col gap-2 md:w-48 shrink-0 flex-wrap" aria-label="Settings">
          <Link href="/dashboard" className="text-sm text-neutral-500 mb-2">
            ← Dashboard
          </Link>
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="text-sm rounded px-2 py-1.5 hover:bg-black/5 dark:hover:bg-white/10">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex-1 flex flex-col gap-4">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {!canEdit && <p className="text-sm text-neutral-500">You have read-only access to this workspace.</p>}
          {children({ tenantId: membership.tenant_id, canEdit })}
        </div>
      </div>
    </div>
  );
}
