import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConversationsPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard/conversations",
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

const mockApi = vi.hoisted(() => ({ listConversations: vi.fn(), exportCsv: vi.fn() }));
vi.mock("@/lib/dashboard-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dashboard-api")>();
  return { ...actual, listConversations: mockApi.listConversations, exportCsv: mockApi.exportCsv };
});

afterEach(() => {
  membership.role = "owner";
  vi.clearAllMocks();
});

describe("ConversationsPage", () => {
  it("renders an empty state when there are no conversations", async () => {
    mockApi.listConversations.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    render(<ConversationsPage />);
    await waitFor(() => expect(screen.getByText(/No conversations found/)).toBeInTheDocument());
  });

  it("renders conversation rows with source and status badges", async () => {
    mockApi.listConversations.mockResolvedValue({
      items: [
        {
          id: "conv-1",
          receptionist_id: "r1",
          started_at: "2026-08-01T10:00:00Z",
          last_message_at: null,
          status: "active",
          source: "widget",
          visitor_reference: null,
          qualification_complete: true,
          had_safety_event: false,
          had_clinic_emergency: false,
        },
      ],
      total: 1,
      limit: 25,
      offset: 0,
    });
    render(<ConversationsPage />);
    await waitFor(() => expect(screen.getByText("Widget")).toBeInTheDocument());
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("Complete")).toBeInTheDocument();
  });
});

describe("ConversationsPage export", () => {
  it("owner sees the export control and it applies the active source filter", async () => {
    mockApi.listConversations.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    mockApi.exportCsv.mockResolvedValue(new Blob(["a"], { type: "text/csv" }));
    render(<ConversationsPage />);

    await waitFor(() => expect(screen.getByText(/No conversations found/)).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Source"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => expect(mockApi.exportCsv).toHaveBeenCalled());
    const [tenantId, entity, , , filters] = mockApi.exportCsv.mock.calls[0];
    expect(tenantId).toBe("tenant-1");
    expect(entity).toBe("conversations");
    expect(filters.sources).toEqual(["test"]);
  });

  it("member does not see the export control", async () => {
    membership.role = "member";
    mockApi.listConversations.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    render(<ConversationsPage />);
    await waitFor(() => expect(screen.getByText(/No conversations found/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Export CSV" })).not.toBeInTheDocument();
  });
});
