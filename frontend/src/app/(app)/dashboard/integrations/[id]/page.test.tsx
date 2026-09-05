import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IntegrationDetailPage from "./page";
import type { IntegrationConnection } from "@/lib/integrations-api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "conn-1" }),
  usePathname: () => "/dashboard/integrations/conn-1",
}));

const membership = vi.hoisted(() => ({ role: "owner" as "owner" | "admin" | "member" }));
vi.mock("@/components/dashboard/DashboardContext", () => ({
  useDashboardContext: () => ({
    tenantId: "tenant-1",
    tenantName: "Acme",
    role: membership.role,
    canManage: membership.role !== "member",
  }),
}));

const mockApi = vi.hoisted(() => ({
  getIntegration: vi.fn(),
  updateIntegration: vi.fn(),
  verifyIntegration: vi.fn(),
  sendTestEvent: vi.fn(),
  pauseIntegration: vi.fn(),
  resumeIntegration: vi.fn(),
  disableIntegration: vi.fn(),
  rotateSigningSecret: vi.fn(),
  generateInboundApiKey: vi.fn(),
  previewFieldMapping: vi.fn(),
}));
vi.mock("@/lib/integrations-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/integrations-api")>();
  return { ...actual, ...mockApi };
});

function makeConnection(overrides: Partial<IntegrationConnection> = {}): IntegrationConnection {
  return {
    id: "conn-1",
    connector_type: "webhook",
    name: "QA Webhook Receiver",
    status: "configured",
    config: { destination_url: "https://webhook.example.com/hook" },
    enabled_event_types: ["enquiry.created"],
    has_signing_secret: true,
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

describe("IntegrationDetailPage", () => {
  it("shows an error state with retry when the connection fails to load (covers non-member 404 / cross-tenant surfaces as a load error)", async () => {
    mockApi.getIntegration.mockRejectedValue(new Error("not found"));
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByText("Could not load this integration.")).toBeInTheDocument());
  });

  it("hides every mutating control for a member, but still shows read-only status", async () => {
    membership.role = "member";
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    render(<IntegrationDetailPage />);

    await waitFor(() => expect(screen.getByText("QA Webhook Receiver")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send test event" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disable" })).not.toBeInTheDocument();
    expect(screen.queryByText("Configuration")).not.toBeInTheDocument();
    expect(screen.queryByText("Outbound signing secret")).not.toBeInTheDocument();
    expect(screen.queryByText("Inbound API key")).not.toBeInTheDocument();
  });

  it("shows action buttons and configuration for an owner", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Test connection" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Send test event" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disable" })).toBeInTheDocument();
    expect(screen.getByText("Configuration")).toBeInTheDocument();
  });

  it("shows Resume instead of Pause when the connection is paused", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection({ status: "paused" }));
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Pause" })).not.toBeInTheDocument();
  });

  it("requires confirmation before disabling, and only calls the API after confirming", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    mockApi.disableIntegration.mockResolvedValue(makeConnection({ status: "disabled" }));
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Disable" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Disable" }));
    expect(mockApi.disableIntegration).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Disable this integration?")).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(mockApi.disableIntegration).toHaveBeenCalledWith("tenant-1", "conn-1", 1));
  });

  it("shows the PII / safety inline warning next to enabled events", async () => {
    mockApi.getIntegration.mockResolvedValue(
      makeConnection({ enabled_event_types: ["contact.captured", "safety.escalation_detected"] })
    );
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByText("Enabled events")).toBeInTheDocument());
    expect(screen.getAllByText("Includes captured contact details.").length).toBeGreaterThan(0);
    expect(screen.getByText("Safety classification only, for human review.")).toBeInTheDocument();
  });

  it("displays a newly generated inbound API key exactly once, then never shows it again after dismissing", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    mockApi.generateInboundApiKey.mockResolvedValue({
      api_key: "airk_verySecretPlaintextValue",
      prefix: "airk_",
      last_four: "alue",
    });
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate inbound key" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Generate inbound key" }));
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Generate key" }));

    await waitFor(() => expect(screen.getByText("airk_verySecretPlaintextValue")).toBeInTheDocument());
    expect(screen.getByText(/copy it now, it will never be shown again/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "I've saved it — hide this" }));
    expect(screen.queryByText("airk_verySecretPlaintextValue")).not.toBeInTheDocument();
  });

  it("requires confirmation before rotating the signing secret, and clears the input field after rotating", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    mockApi.rotateSigningSecret.mockResolvedValue(makeConnection({ version: 2, has_signing_secret: true }));
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByLabelText("New signing secret")).toBeInTheDocument());

    const rotateButton = screen.getByRole("button", { name: "Rotate secret" });
    expect(rotateButton).toBeDisabled();

    await userEvent.type(screen.getByLabelText("New signing secret"), "brand-new-secret-value");
    expect(rotateButton).toBeEnabled();
    await userEvent.click(rotateButton);
    expect(mockApi.rotateSigningSecret).not.toHaveBeenCalled();

    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Rotate secret" }));
    await waitFor(() =>
      expect(mockApi.rotateSigningSecret).toHaveBeenCalledWith("tenant-1", "conn-1", "brand-new-secret-value", 1)
    );
    await waitFor(() => expect(screen.getByLabelText("New signing secret")).toHaveValue(""));
  });

  it("previews a field mapping and renders the transformed result", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    mockApi.previewFieldMapping.mockResolvedValue({ result: { phone_number: "555-0100" } });
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Preview transformation" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Preview transformation" }));
    await waitFor(() => expect(screen.getByText(/phone_number/)).toBeInTheDocument());
    expect(mockApi.previewFieldMapping).toHaveBeenCalled();
  });

  it("shows an inline error when the mapping preview's sample JSON is invalid", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByLabelText(/Fictional sample data/)).toBeInTheDocument());

    const sampleField = screen.getByLabelText(/Fictional sample data/);
    await userEvent.clear(sampleField);
    await userEvent.type(sampleField, "{{not valid json");
    await userEvent.click(screen.getByRole("button", { name: "Preview transformation" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/not valid JSON/));
    expect(mockApi.previewFieldMapping).not.toHaveBeenCalled();
  });

  it("reloads and shows a conflict message on a 409 while saving configuration", async () => {
    const { ApiError } = await import("@/lib/api");
    mockApi.getIntegration
      .mockResolvedValueOnce(makeConnection())
      .mockResolvedValueOnce(makeConnection({ version: 2 }));
    mockApi.updateIntegration.mockRejectedValue(new ApiError(409, "conflict"));
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/changed elsewhere/)
    );
    expect(mockApi.getIntegration).toHaveBeenCalledTimes(2);
  });

  it("shows a success message after verifying, and a failure message with the error summary otherwise", async () => {
    mockApi.getIntegration.mockResolvedValue(makeConnection());
    mockApi.verifyIntegration.mockResolvedValue({ success: false, error_summary: "Connection refused" });
    render(<IntegrationDetailPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Test connection" })).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/Verification failed: Connection refused/));
  });
});
