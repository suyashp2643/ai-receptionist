import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HandoffDetailPage from "./page";
import { ApiError } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard/handoffs/h1",
  useParams: () => ({ id: "h1" }),
}));

const membership = vi.hoisted(() => ({ role: "owner" as "owner" | "member" }));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme", tenant_slug: "acme", role: membership.role, status: "active" }],
    isLoading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("@/components/dashboard/DashboardContext", () => ({
  useDashboardContext: () => ({
    tenantId: "tenant-1",
    tenantName: "Acme",
    role: membership.role,
    canManage: membership.role !== "member",
  }),
}));

const mockApi = vi.hoisted(() => ({
  getHandoffDetail: vi.fn(),
  claimHandoff: vi.fn(),
  updateHandoffStatus: vi.fn(),
  listNotes: vi.fn(async () => []),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));
vi.mock("@/lib/dashboard-api", () => mockApi);

const openHandoff = {
  id: "h1",
  contact_id: null,
  conversation_id: "conv-1",
  receptionist_id: "r1",
  reason: "Call me back",
  urgency: "normal",
  preferred_contact_method: null,
  status: "open",
  assigned_user_id: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  resolved_at: null,
  version: 1,
  is_clinic_emergency: false,
};

describe("HandoffDetailPage", () => {
  it("claims an open handoff", async () => {
    membership.role = "member";
    mockApi.getHandoffDetail.mockResolvedValue(openHandoff);
    mockApi.claimHandoff.mockResolvedValue({ ...openHandoff, status: "claimed", assigned_user_id: "u1", version: 2 });
    render(<HandoffDetailPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Claim" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Claim" }));

    await waitFor(() => expect(mockApi.claimHandoff).toHaveBeenCalledWith("tenant-1", "h1"));
  });

  it("shows a conflict message when the handoff was already claimed", async () => {
    membership.role = "member";
    mockApi.getHandoffDetail.mockResolvedValue(openHandoff);
    mockApi.claimHandoff.mockRejectedValue(new ApiError(409, "This handoff is no longer open."));
    render(<HandoffDetailPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Claim" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Claim" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/already claimed/));
  });

  it("hides the cancel action for a member", async () => {
    membership.role = "member";
    mockApi.getHandoffDetail.mockResolvedValue(openHandoff);
    render(<HandoffDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Claim" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("shows the cancel action for an owner", async () => {
    membership.role = "owner";
    mockApi.getHandoffDetail.mockResolvedValue(openHandoff);
    render(<HandoffDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument());
  });

  it("labels a clinic-emergency handoff distinctly", async () => {
    membership.role = "owner";
    mockApi.getHandoffDetail.mockResolvedValue({ ...openHandoff, is_clinic_emergency: true });
    render(<HandoffDetailPage />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/clinic-emergency safety response/));
  });
});
