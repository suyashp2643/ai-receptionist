import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import IntegrationsPage from "./page";
import type { IntegrationConnection, TenantIntegrationHealth } from "@/lib/integrations-api";

const membership = vi.hoisted(() => ({ role: "owner" as "owner" | "admin" | "member" }));
vi.mock("@/components/dashboard/DashboardContext", () => ({
  useDashboardContext: () => ({
    tenantId: "tenant-1",
    tenantName: "Acme",
    role: membership.role,
    canManage: membership.role !== "member",
  }),
}));

const mockApi = vi.hoisted(() => ({ listIntegrations: vi.fn(), getIntegrationHealth: vi.fn() }));
vi.mock("@/lib/integrations-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/integrations-api")>();
  return { ...actual, listIntegrations: mockApi.listIntegrations, getIntegrationHealth: mockApi.getIntegrationHealth };
});

const emptyHealth: TenantIntegrationHealth = {
  window_hours: 24,
  connections: { active: 0, paused: 0, failing: 0, disabled: 0, total: 0 },
  pending_events: 0,
  retry_backlog: 0,
  oldest_pending_age_seconds: null,
  dead_letter_count: 0,
  successful_deliveries: 0,
  failed_deliveries: 0,
  success_rate: null,
  latency: { p50_ms: null, p95_ms: null, sample_size: 0 },
  last_success_at: null,
  last_failure_at: null,
  warnings: [],
};

function makeConnection(overrides: Partial<IntegrationConnection> = {}): IntegrationConnection {
  return {
    id: "conn-1",
    connector_type: "mock",
    name: "Test Connection",
    status: "configured",
    config: {},
    enabled_event_types: [],
    has_signing_secret: false,
    inbound_api_key_prefix: null,
    inbound_api_key_last_four: null,
    failure_count: 0,
    last_verified_at: null,
    last_delivery_at: null,
    last_delivery_status: null,
    last_inbound_event_at: null,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  membership.role = "owner";
  vi.clearAllMocks();
});

describe("IntegrationsPage", () => {
  it("shows a loading state before data resolves", () => {
    mockApi.listIntegrations.mockReturnValue(new Promise(() => {}));
    mockApi.getIntegrationHealth.mockReturnValue(new Promise(() => {}));
    render(<IntegrationsPage />);
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
  });

  it("shows an empty state with an owner-facing hint when there are no integrations", async () => {
    mockApi.listIntegrations.mockResolvedValue({ items: [] });
    mockApi.getIntegrationHealth.mockResolvedValue(emptyHealth);
    render(<IntegrationsPage />);
    await waitFor(() => expect(screen.getByText("No integrations found")).toBeInTheDocument());
    expect(screen.getByText(/Create a connection to send events/)).toBeInTheDocument();
  });

  it("shows a member-facing empty-state hint and hides the New integration link for a member", async () => {
    membership.role = "member";
    mockApi.listIntegrations.mockResolvedValue({ items: [] });
    mockApi.getIntegrationHealth.mockResolvedValue(emptyHealth);
    render(<IntegrationsPage />);
    await waitFor(() => expect(screen.getByText("No integrations found")).toBeInTheDocument());
    expect(screen.getByText(/An owner or admin has not configured/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New integration" })).not.toBeInTheDocument();
  });

  it("shows an error state with a retry option when the list fails to load", async () => {
    mockApi.listIntegrations.mockRejectedValue(new Error("network error"));
    mockApi.getIntegrationHealth.mockResolvedValue(emptyHealth);
    render(<IntegrationsPage />);
    await waitFor(() => expect(screen.getByText("Could not load integrations.")).toBeInTheDocument());
  });

  it("renders connections in a table with status and lists health summary counts", async () => {
    mockApi.listIntegrations.mockResolvedValue({
      items: [makeConnection({ id: "conn-1", name: "Revenue Brain Prod", status: "verified", failure_count: 0 })],
    });
    mockApi.getIntegrationHealth.mockResolvedValue({
      ...emptyHealth,
      connections: { active: 1, paused: 0, failing: 0, disabled: 0, total: 1 },
      pending_events: 3,
    });
    render(<IntegrationsPage />);
    await waitFor(() => expect(screen.getByRole("link", { name: "Revenue Brain Prod" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Revenue Brain Prod" })).toHaveAttribute(
      "href",
      "/dashboard/integrations/conn-1"
    );
    expect(screen.getByText("Pending events")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders health warnings returned by the backend", async () => {
    mockApi.listIntegrations.mockResolvedValue({ items: [] });
    mockApi.getIntegrationHealth.mockResolvedValue({
      ...emptyHealth,
      warnings: [{ code: "missing_encryption_key", message: "Integration encryption is not configured.", connection_id: null }],
    });
    render(<IntegrationsPage />);
    await waitFor(() =>
      expect(screen.getByText("Integration encryption is not configured.")).toBeInTheDocument()
    );
  });

  it("filters the table by connector type", async () => {
    mockApi.listIntegrations.mockResolvedValue({
      items: [
        makeConnection({ id: "conn-1", name: "Mock One", connector_type: "mock" }),
        makeConnection({ id: "conn-2", name: "Webhook One", connector_type: "webhook" }),
      ],
    });
    mockApi.getIntegrationHealth.mockResolvedValue(emptyHealth);
    render(<IntegrationsPage />);
    await waitFor(() => expect(screen.getByRole("link", { name: "Mock One" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Webhook One" })).toBeInTheDocument();

    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.selectOptions(screen.getByLabelText("Connector type"), "webhook");

    expect(screen.queryByRole("link", { name: "Mock One" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Webhook One" })).toBeInTheDocument();
  });
});
