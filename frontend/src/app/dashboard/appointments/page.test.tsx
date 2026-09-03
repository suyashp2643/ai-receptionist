import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AppointmentsPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard/appointments",
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner", status: "active" }],
    isLoading: false,
    logout: vi.fn(),
  }),
}));

const membership = vi.hoisted(() => ({ role: "owner" as "owner" | "member" }));
vi.mock("@/components/dashboard/DashboardContext", () => ({
  useDashboardContext: () => ({
    tenantId: "tenant-1",
    tenantName: "Acme",
    role: membership.role,
    canManage: membership.role !== "member",
  }),
}));

const mockApi = vi.hoisted(() => ({ listAppointments: vi.fn(), exportCsv: vi.fn() }));
vi.mock("@/lib/dashboard-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dashboard-api")>();
  return { ...actual, listAppointments: mockApi.listAppointments, exportCsv: mockApi.exportCsv };
});

afterEach(() => {
  membership.role = "owner";
  vi.clearAllMocks();
});

describe("AppointmentsPage", () => {
  it("renders an empty state when there are no appointment requests", async () => {
    mockApi.listAppointments.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    render(<AppointmentsPage />);
    await waitFor(() => expect(screen.getByText(/No appointment requests found/)).toBeInTheDocument());
  });
});

describe("AppointmentsPage export", () => {
  it("owner can export with the active status filter applied", async () => {
    mockApi.listAppointments.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    mockApi.exportCsv.mockResolvedValue(new Blob(["a"], { type: "text/csv" }));
    render(<AppointmentsPage />);
    await waitFor(() => expect(screen.getByText(/No appointment requests found/)).toBeInTheDocument());

    await userEvent.selectOptions(screen.getByLabelText("Status"), "pending");
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => expect(mockApi.exportCsv).toHaveBeenCalled());
    const [tenantId, entity, , , filters] = mockApi.exportCsv.mock.calls[0];
    expect(tenantId).toBe("tenant-1");
    expect(entity).toBe("appointments");
    expect(filters.statuses).toEqual(["pending"]);
  });

  it("member does not see the export control", async () => {
    membership.role = "member";
    mockApi.listAppointments.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    render(<AppointmentsPage />);
    await waitFor(() => expect(screen.getByText(/No appointment requests found/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Export CSV" })).not.toBeInTheDocument();
  });
});
