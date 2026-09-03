"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { DashboardContext } from "./DashboardContext";

// One flat list, used for both the desktop top nav and the mobile drawer —
// no separate "hidden in a menu" tier. Settings/Test console/Widget are
// full nav items, not tucked away in the user menu (see docs/PROGRESS.md's
// Phase 6 follow-up for why: an earlier version buried them there).
const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/conversations", label: "Conversations" },
  { href: "/dashboard/contacts", label: "Contacts" },
  { href: "/dashboard/enquiries", label: "Enquiries" },
  { href: "/dashboard/appointments", label: "Appointments" },
  { href: "/dashboard/handoffs", label: "Handoffs" },
  { href: "/dashboard/activity", label: "Activity" },
  { href: "/dashboard/settings/business-profile", label: "Settings" },
  { href: "/dashboard/receptionist/test", label: "Test console" },
  { href: "/dashboard/receptionist/widget", label: "Widget" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  if (href === "/dashboard/settings/business-profile") return pathname.startsWith("/dashboard/settings");
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The one dashboard chrome — rendered once by `app/dashboard/layout.tsx`,
 * never per-page. Every page under `/dashboard/*` (Overview, Conversations,
 * Contacts, Enquiries, Appointments, Handoffs, Activity, Settings, Test
 * console, Widget management) renders as `children` inside this same
 * header/nav, so there is exactly one shell instance per navigation, never
 * a nested or duplicated one. Handles auth loading/redirect centrally —
 * `children` is never rendered until a membership is resolved, so no page
 * needs its own loading/redirect boilerplate. */
export function DashboardShell({ children }: { children: ReactNode }) {
  const { user, memberships, isLoading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const membership = memberships[0];

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-950">
        <p className="text-neutral-500" role="status">
          Loading…
        </p>
      </div>
    );
  }
  if (!user || !membership) return null;

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className="min-h-screen flex flex-col bg-neutral-50 dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100">
      <header className="border-b border-black/10 dark:border-white/10 bg-white dark:bg-neutral-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              className="md:hidden rounded p-2 hover:bg-black/5 dark:hover:bg-white/10"
              aria-label={mobileNavOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={mobileNavOpen}
              aria-controls="dashboard-mobile-nav"
              onClick={() => setMobileNavOpen((v) => !v)}
            >
              <span aria-hidden="true">{mobileNavOpen ? "✕" : "☰"}</span>
            </button>
            <Link href="/dashboard" className="font-semibold tracking-tight truncate">
              {membership.tenant_name}
            </Link>
            <span className="hidden sm:inline text-xs uppercase tracking-wide rounded-full px-2 py-0.5 bg-black/5 dark:bg-white/10 text-neutral-600 dark:text-neutral-300">
              {membership.role}
            </span>
          </div>

          <nav
            className="hidden md:flex items-center gap-1 overflow-x-auto"
            aria-label="Main navigation"
          >
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(pathname, item.href) ? "page" : undefined}
                className={`text-sm rounded px-2.5 py-1.5 whitespace-nowrap ${
                  isActive(pathname, item.href)
                    ? "bg-foreground text-background font-medium"
                    : "hover:bg-black/5 dark:hover:bg-white/10"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="relative shrink-0">
            <button
              type="button"
              className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-black/5 dark:hover:bg-white/10"
              aria-haspopup="menu"
              aria-expanded={userMenuOpen}
              onClick={() => setUserMenuOpen((v) => !v)}
            >
              <span className="truncate max-w-[10rem]">{user.display_name}</span>
              <span aria-hidden="true">▾</span>
            </button>
            {userMenuOpen && (
              <div
                role="menu"
                className="absolute right-0 mt-1 w-56 rounded-md border border-black/10 dark:border-white/15 bg-white dark:bg-neutral-900 shadow-lg py-1 z-20"
              >
                <div className="px-3 py-2 text-xs text-neutral-500 border-b border-black/5 dark:border-white/10">
                  Signed in as
                  <div className="text-neutral-800 dark:text-neutral-200 truncate">{user.normalized_email}</div>
                </div>
                <button
                  role="menuitem"
                  type="button"
                  onClick={handleLogout}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-black/5 dark:hover:bg-white/10"
                >
                  Log out
                </button>
              </div>
            )}
          </div>
        </div>

        {mobileNavOpen && (
          <nav
            id="dashboard-mobile-nav"
            className="md:hidden border-t border-black/10 dark:border-white/10 px-4 py-2 flex flex-col gap-1"
            aria-label="Main navigation"
          >
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(pathname, item.href) ? "page" : undefined}
                onClick={() => setMobileNavOpen(false)}
                className={`text-sm rounded px-3 py-2 ${
                  isActive(pathname, item.href) ? "bg-foreground text-background font-medium" : "hover:bg-black/5 dark:hover:bg-white/10"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
        <DashboardContext.Provider
          value={{
            tenantId: membership.tenant_id,
            tenantName: membership.tenant_name,
            role: membership.role,
            canManage: membership.role === "owner" || membership.role === "admin",
          }}
        >
          {children}
        </DashboardContext.Provider>
      </main>
    </div>
  );
}
