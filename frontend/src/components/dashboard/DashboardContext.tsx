"use client";

import { createContext, useContext } from "react";

export interface DashboardContextValue {
  tenantId: string;
  tenantName: string;
  role: "owner" | "admin" | "member";
  canManage: boolean;
}

export const DashboardContext = createContext<DashboardContextValue | null>(null);

/** Every page under `/dashboard/*` renders inside `app/dashboard/layout.tsx`
 * (via `DashboardShell`), which never renders `children` until auth has
 * resolved and a membership exists — so a page calling this can assume the
 * value is always present. Thrown only if a component is rendered outside
 * that layout (a programming error, not a runtime user-facing state). */
export function useDashboardContext(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboardContext must be used within the dashboard layout (app/dashboard/layout.tsx)");
  return ctx;
}
