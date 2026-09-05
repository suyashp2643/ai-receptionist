import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DashboardShell } from "./DashboardShell";
import { SettingsShell } from "@/app/(app)/dashboard/settings/SettingsShell";
import { useDashboardContext } from "./DashboardContext";

let currentPathname = "/dashboard";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => currentPathname,
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme Dental", tenant_slug: "acme", role: "owner", status: "active" }],
    isLoading: false,
    logout: vi.fn(),
  }),
}));

/** A minimal stand-in for a "new" Phase 6 page body — proves the same
 * DashboardContext the shell provides is what a real Phase 6 page
 * (conversations/contacts/enquiries/etc, all built the same way) reads. */
function NewStylePageBody() {
  const { tenantId, tenantName, role } = useDashboardContext();
  return (
    <p data-testid="new-page-body">
      New-style page for {tenantName} ({tenantId}), role {role}
    </p>
  );
}

describe("DashboardShell — unified across old and new pages", () => {
  it("renders a representative OLD-style page (SettingsShell) inside exactly one shell", () => {
    currentPathname = "/dashboard/settings/business-profile";
    render(
      <DashboardShell>
        <SettingsShell title="Business profile">{({ tenantId }) => <p data-testid="old-page-body">Old-style settings body for {tenantId}</p>}</SettingsShell>
      </DashboardShell>
    );

    // Exactly one header/nav — never a nested or duplicated shell.
    expect(screen.getAllByRole("banner").length).toBe(1);
    expect(screen.getAllByLabelText("Main navigation").length).toBe(1);
    // Tenant identity and role, resolved once by the shell.
    expect(screen.getByText("Acme Dental")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    // The old page's own content, and its own settings sub-nav, both render.
    expect(screen.getByTestId("old-page-body")).toHaveTextContent("tenant-1");
    expect(screen.getByRole("link", { name: "Receptionist" })).toBeInTheDocument();
    // Settings is the active top-level nav item for a /dashboard/settings/* route.
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
  });

  it("renders a representative NEW-style page (a Phase 6 body reading DashboardContext) inside the same shell shape", () => {
    currentPathname = "/dashboard/conversations";
    render(
      <DashboardShell>
        <NewStylePageBody />
      </DashboardShell>
    );

    expect(screen.getAllByRole("banner").length).toBe(1);
    expect(screen.getByTestId("new-page-body")).toHaveTextContent("Acme Dental");
    expect(screen.getByTestId("new-page-body")).toHaveTextContent("tenant-1");
    expect(screen.getByTestId("new-page-body")).toHaveTextContent("owner");
    expect(screen.getByRole("link", { name: "Conversations" })).toHaveAttribute("aria-current", "page");
    // A different section is correctly NOT marked active.
    expect(screen.getByRole("link", { name: "Settings" })).not.toHaveAttribute("aria-current");
  });

  it("includes Settings, Test console, and Widget as direct top-level nav links, not hidden in a menu", () => {
    currentPathname = "/dashboard";
    render(
      <DashboardShell>
        <p>content</p>
      </DashboardShell>
    );
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Test console" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Widget" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Integrations" })).toBeInTheDocument();
  });

  it("supports mobile navigation via the hamburger toggle", async () => {
    currentPathname = "/dashboard";
    render(
      <DashboardShell>
        <p>content</p>
      </DashboardShell>
    );
    expect(screen.queryByRole("navigation", { name: "Main navigation", hidden: false })).toBeTruthy();
    const toggle = screen.getByRole("button", { name: "Open navigation menu" });
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close navigation menu" })).toBeInTheDocument();
    // The mobile drawer renders the same full nav, including Settings/Test/Widget.
    const mobileNav = document.getElementById("dashboard-mobile-nav");
    expect(mobileNav).not.toBeNull();
    expect(mobileNav).toHaveTextContent("Settings");
    expect(mobileNav).toHaveTextContent("Test console");
    expect(mobileNav).toHaveTextContent("Widget");
  });
});
