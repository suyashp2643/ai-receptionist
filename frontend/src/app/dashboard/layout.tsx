import { DashboardShell } from "@/components/dashboard/DashboardShell";

/** Wraps every route under `/dashboard/*` — Overview, Conversations,
 * Contacts, Enquiries, Appointments, Handoffs, Activity, Settings, the
 * private test console, and widget installation management — in exactly
 * one dashboard shell instance. Next.js renders this layout once per
 * navigation within `/dashboard`, not once per page, so there is never a
 * nested or duplicated header/nav. */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
