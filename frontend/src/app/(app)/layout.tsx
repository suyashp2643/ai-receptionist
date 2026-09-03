import type { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth-context";

/** Wraps every authenticated-app route (login, register, onboarding,
 * dashboard) in AuthProvider. Deliberately NOT applied at the root layout
 * (see frontend/src/app/layout.tsx) — the public marketing site
 * ((marketing) route group) must never trigger a token-refresh call or
 * reference dashboard auth state on a static page it doesn't need
 * (Phase 7 security/performance requirement). */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
