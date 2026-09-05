import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DashboardShell } from "./DashboardShell";

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/dashboard/integrations/conn-1",
}));

const auth = vi.hoisted(() => ({
  user: null as { id: string; normalized_email: string; display_name: string; is_active: boolean; last_login_at: string | null; created_at: string } | null,
  memberships: [] as unknown[],
  isLoading: true,
}));
vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ ...auth, logout: vi.fn() }),
}));

afterEach(() => {
  auth.user = null;
  auth.memberships = [];
  auth.isLoading = true;
  vi.clearAllMocks();
});

describe("DashboardShell — redirect guard (loading vs. unauthenticated vs. authenticated)", () => {
  it("does not redirect while auth is still resolving (loading state)", async () => {
    auth.isLoading = true;
    auth.user = null;
    render(
      <DashboardShell>
        <p>page content</p>
      </DashboardShell>
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    // Give any stray effect a tick to fire — it must not.
    await new Promise((r) => setTimeout(r, 10));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("redirects to /login exactly once when auth resolves to unauthenticated — no redirect storm", async () => {
    auth.isLoading = false;
    auth.user = null;
    const { rerender } = render(
      <DashboardShell>
        <p>page content</p>
      </DashboardShell>
    );

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(router.replace).toHaveBeenCalledTimes(1);

    // Re-rendering (e.g. a parent re-render, or React re-running effects)
    // with the same resolved-unauthenticated state must not fire it again.
    rerender(
      <DashboardShell>
        <p>page content</p>
      </DashboardShell>
    );
    await new Promise((r) => setTimeout(r, 10));
    expect(router.replace).toHaveBeenCalledTimes(1);
  });

  it("never redirects, and renders the originally requested page, once auth resolves to authenticated", async () => {
    auth.isLoading = false;
    auth.user = { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" };
    auth.memberships = [{ tenant_id: "t1", tenant_name: "Acme", tenant_slug: "acme", role: "owner", status: "active" }];

    render(
      <DashboardShell>
        <p>page content</p>
      </DashboardShell>
    );

    await waitFor(() => expect(screen.getByText("page content")).toBeInTheDocument());
    expect(router.replace).not.toHaveBeenCalled();
  });
});
