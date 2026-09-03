import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EnquiryDetailPage from "./page";
import { ApiError } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard/enquiries/enq-1",
  useParams: () => ({ id: "enq-1" }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner", status: "active" }],
    isLoading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("@/components/dashboard/DashboardContext", () => ({
  useDashboardContext: () => ({ tenantId: "tenant-1", tenantName: "Acme", role: "owner", canManage: true }),
}));

const mockApi = vi.hoisted(() => ({
  getEnquiryDetail: vi.fn(),
  updateEnquiryStatus: vi.fn(),
  listNotes: vi.fn(async () => []),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
  ENQUIRY_STATUSES: ["new", "qualified", "contacted", "appointment_requested", "in_progress", "won", "lost", "archived"],
}));
vi.mock("@/lib/dashboard-api", () => mockApi);

const detail = {
  id: "enq-1",
  contact_id: "c1",
  conversation_id: "conv-1",
  receptionist_id: "r1",
  source: "widget",
  status: "new",
  qualification_data: { budget: "under 300k" },
  qualification_complete: false,
  recommended_next_action: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  version: 1,
};

describe("EnquiryDetailPage", () => {
  it("updates status and reflects the new version", async () => {
    mockApi.getEnquiryDetail.mockResolvedValue(detail);
    mockApi.updateEnquiryStatus.mockResolvedValue({ ...detail, status: "qualified", version: 2 });
    render(<EnquiryDetailPage />);

    await waitFor(() => expect(screen.getByLabelText("Change status")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Change status"), "qualified");

    await waitFor(() => expect(mockApi.updateEnquiryStatus).toHaveBeenCalledWith("tenant-1", "enq-1", "qualified", 1));
  });

  it("shows a conflict message and reloads on a 409", async () => {
    mockApi.getEnquiryDetail.mockResolvedValueOnce(detail).mockResolvedValueOnce({ ...detail, status: "contacted", version: 3 });
    mockApi.updateEnquiryStatus.mockRejectedValue(new ApiError(409, "This record was changed by someone else."));
    render(<EnquiryDetailPage />);

    await waitFor(() => expect(screen.getByLabelText("Change status")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Change status"), "qualified");

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/changed by someone else/));
  });

  it("never displays a revenue figure anywhere on the page", async () => {
    mockApi.getEnquiryDetail.mockResolvedValue(detail);
    render(<EnquiryDetailPage />);
    await waitFor(() => expect(screen.getByText(/does not calculate revenue/)).toBeInTheDocument());
    expect(document.body.textContent).not.toMatch(/\$\d/);
  });
});
