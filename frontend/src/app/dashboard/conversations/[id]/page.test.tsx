import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import ConversationDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard/conversations/conv-1",
  useParams: () => ({ id: "conv-1" }),
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
  getConversationDetail: vi.fn(),
  listNotes: vi.fn(async () => []),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));
vi.mock("@/lib/dashboard-api", () => mockApi);

const detail = {
  id: "conv-1",
  receptionist_id: "r1",
  source: "widget",
  status: "active",
  provider: "mock",
  locale: "en",
  started_at: "2026-08-01T10:00:00Z",
  last_message_at: null,
  completed_at: null,
  qualification_complete: true,
  collected_data: {},
  had_safety_event: false,
  had_clinic_emergency: false,
  messages: [
    {
      id: "m1",
      role: "user",
      content: "What are your hours?",
      sequence_number: 0,
      citations: [],
      safety_labels: [],
      tool_name: null,
      tool_input: null,
      tool_output: null,
      created_at: "2026-08-01T10:00:01Z",
    },
  ],
  message_total: 1,
  message_limit: 200,
  message_offset: 0,
  summary: null,
  contact: null,
  enquiry: null,
  appointment_requests: [],
  handoffs: [],
};

describe("ConversationDetailPage", () => {
  it("renders the transcript and never exposes internal fields", async () => {
    mockApi.getConversationDetail.mockResolvedValue(detail);
    render(<ConversationDetailPage />);

    await waitFor(() => expect(screen.getByText("What are your hours?")).toBeInTheDocument());
    const bodyText = document.body.textContent ?? "";
    expect(bodyText).not.toMatch(/system.prompt/i);
    expect(bodyText).not.toMatch(/capability.token/i);
    expect(bodyText).not.toMatch(/token_hash/i);
  });

  it("surfaces the clinic emergency flag distinctly from an ordinary safety event", async () => {
    mockApi.getConversationDetail.mockResolvedValue({ ...detail, had_safety_event: true, had_clinic_emergency: true });
    render(<ConversationDetailPage />);
    await waitFor(() => expect(screen.getByText(/Clinic emergency/)).toBeInTheDocument());
  });
});
