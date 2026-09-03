import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import DashboardPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
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

vi.mock("@/lib/phase3-api", () => ({
  getOnboardingState: vi.fn(async () => ({
    status: "completed",
    completed_at: "2026-01-01T00:00:00Z",
    ready_to_complete: true,
    steps: {},
    incomplete_requirements: [],
    business_profile: null,
  })),
  listReceptionists: vi.fn(async () => [{ id: "r1", name: "Sam" }]),
}));

const baseOverview = {
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  receptionist_id: null,
  include_test_preview: false,
  total_conversations: 10,
  genuine_widget_conversations: 8,
  preview_conversations: 1,
  test_conversations: 1,
  unique_visitor_sessions: 9,
  contacts_captured: 4,
  contact_capture_rate: 0.5,
  enquiries_created: 5,
  qualified_enquiries: 2,
  qualification_completion_rate: 0.4,
  appointment_requests: 3,
  pending_appointments: 2,
  confirmed_appointments: 1,
  human_handoffs: 2,
  open_handoffs: 1,
  resolved_handoffs: 1,
  unanswered_or_fallback_responses: 0,
  safety_interventions: 0,
  average_first_response_time_seconds: 12.5,
  average_conversation_length_messages: 4.2,
  conversation_completion_rate: 0.7,
  estimated_staff_time_saved_minutes: 40,
  estimated_staff_time_saved_minutes_is_estimate: true,
};

const mockApi = vi.hoisted(() => ({
  getAnalyticsOverview: vi.fn(),
  getAnalyticsTimeseries: vi.fn(),
}));

vi.mock("@/lib/dashboard-api", () => mockApi);

describe("DashboardPage overview", () => {
  it("renders real KPI values from the API, never invented ones", async () => {
    mockApi.getAnalyticsOverview.mockResolvedValue(baseOverview);
    mockApi.getAnalyticsTimeseries.mockResolvedValue({ points: [] });

    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("10")).toBeInTheDocument());
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText(/Estimate only/)).toBeInTheDocument();
  });

  it("shows a dash, never 0% or NaN, for a null rate", async () => {
    mockApi.getAnalyticsOverview.mockResolvedValue({
      ...baseOverview,
      contact_capture_rate: null,
      qualification_completion_rate: null,
      conversation_completion_rate: null,
      average_first_response_time_seconds: null,
      average_conversation_length_messages: null,
    });
    mockApi.getAnalyticsTimeseries.mockResolvedValue({ points: [] });

    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("10")).toBeInTheDocument());
    expect(screen.queryByText("NaN%")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("shows an error state and allows retry when analytics fail to load", async () => {
    mockApi.getAnalyticsOverview.mockRejectedValue(new Error("network error"));
    mockApi.getAnalyticsTimeseries.mockResolvedValue({ points: [] });

    render(<DashboardPage />);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText(/Could not load analytics/)).toBeInTheDocument();
  });
});
