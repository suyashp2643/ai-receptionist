"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useDashboardContext } from "@/components/dashboard/DashboardContext";

const NAV = [
  { href: "/dashboard/settings/business-profile", label: "Business profile" },
  { href: "/dashboard/settings/receptionist", label: "Receptionist" },
  { href: "/dashboard/settings/locations", label: "Locations" },
  { href: "/dashboard/settings/services", label: "Services" },
  { href: "/dashboard/settings/knowledge", label: "Knowledge & FAQs" },
  { href: "/dashboard/settings/qualification", label: "Qualification" },
  { href: "/dashboard/settings/actions", label: "Actions" },
];

/** The settings section's own sub-navigation, rendered inside the unified
 * dashboard shell's content area (see app/dashboard/layout.tsx) — this is
 * a second-level nav specific to /dashboard/settings/*, not a competing
 * top-level shell. Auth/loading/tenant resolution is handled once, by the
 * layout; this component only reads the already-resolved context. */
export function SettingsShell({
  title,
  children,
}: {
  title: string;
  children: (ctx: { tenantId: string; canEdit: boolean }) => ReactNode;
}) {
  const { tenantId, canManage } = useDashboardContext();
  const pathname = usePathname();

  return (
    <div className="flex flex-col md:flex-row gap-8">
      <nav className="flex md:flex-col gap-2 md:w-48 shrink-0 flex-wrap" aria-label="Settings">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={pathname === item.href ? "page" : undefined}
            className={`text-sm rounded px-2 py-1.5 ${
              pathname === item.href ? "bg-black/5 dark:bg-white/10 font-medium" : "hover:bg-black/5 dark:hover:bg-white/10"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="flex-1 flex flex-col gap-4">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {!canManage && <p className="text-sm text-neutral-500">You have read-only access to this workspace.</p>}
        {children({ tenantId, canEdit: canManage })}
      </div>
    </div>
  );
}
