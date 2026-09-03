import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WidgetInstallationPage from "./page";

const push = vi.fn();
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme", tenant_slug: "acme", role: "owner", status: "active" }],
    isLoading: false,
  }),
}));

vi.mock("@/components/dashboard/DashboardContext", () => ({
  useDashboardContext: () => ({ tenantId: "tenant-1", tenantName: "Acme", role: "owner", canManage: true }),
}));

vi.mock("@/lib/phase3-api", () => ({
  listReceptionists: vi.fn(async () => [
    {
      id: "receptionist-1",
      tenant_id: "tenant-1",
      industry_template_id: null,
      template_version: null,
      name: "Ada",
      welcome_message: "Hi!",
      tone: "friendly",
      default_language: "en",
      supported_languages: [],
      logo_url: null,
      accent_color: null,
      suggested_questions: [],
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ]),
  listServices: vi.fn(async () => []),
  listLocations: vi.fn(async () => []),
}));

const baseInstallation = {
  id: "install-1",
  tenant_id: "tenant-1",
  receptionist_id: "receptionist-1",
  public_id: "pub-abc123",
  status: "draft" as const,
  allowed_domains: [] as string[],
  theme: {},
  launcher_position: "bottom-right",
  privacy_notice: "",
  ai_disclosure: "This is a mock AI demonstration.",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  revoked_at: null,
};

const mockApi = vi.hoisted(() => ({
  listWidgetInstallations: vi.fn(),
  createWidgetInstallation: vi.fn(),
  getWidgetEmbedSnippet: vi.fn(),
  updateWidgetInstallation: vi.fn(),
  activateWidgetInstallation: vi.fn(),
  pauseWidgetInstallation: vi.fn(),
  revokeWidgetInstallation: vi.fn(),
  listWidgetContacts: vi.fn(),
  listWidgetEnquiries: vi.fn(),
  listWidgetAppointmentRequests: vi.fn(),
  listWidgetHandoffRequests: vi.fn(),
}));

vi.mock("@/lib/widget-installations-api", () => mockApi);

function setupDefaultMocks() {
  mockApi.listWidgetInstallations.mockResolvedValue([]);
  mockApi.createWidgetInstallation.mockResolvedValue({ ...baseInstallation });
  mockApi.getWidgetEmbedSnippet.mockResolvedValue({
    ...baseInstallation,
    embed_snippet: '<script\n  src="http://localhost:5174/widget.js"\n  data-receptionist-id="pub-abc123"\n  async\n></script>',
    widget_bundle_url: "http://localhost:5174/widget.js",
  });
  mockApi.updateWidgetInstallation.mockResolvedValue({ ...baseInstallation, allowed_domains: ["example.com"] });
  mockApi.activateWidgetInstallation.mockResolvedValue({ ...baseInstallation, status: "active" });
  mockApi.pauseWidgetInstallation.mockResolvedValue({ ...baseInstallation, status: "paused" });
  mockApi.revokeWidgetInstallation.mockResolvedValue({ ...baseInstallation, status: "revoked", revoked_at: "2026-01-02T00:00:00Z" });
  mockApi.listWidgetContacts.mockResolvedValue([]);
  mockApi.listWidgetEnquiries.mockResolvedValue([]);
  mockApi.listWidgetAppointmentRequests.mockResolvedValue([]);
  mockApi.listWidgetHandoffRequests.mockResolvedValue([]);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("WidgetInstallationPage", () => {
  it("shows the mock AI demonstration badge", async () => {
    setupDefaultMocks();
    render(<WidgetInstallationPage />);
    expect(await screen.findByText("Mock AI demonstration")).toBeInTheDocument();
  });

  it("creates a widget installation for the selected receptionist", async () => {
    setupDefaultMocks();
    const user = userEvent.setup();
    render(<WidgetInstallationPage />);

    await waitFor(() => expect(screen.getByText("Ada")).toBeInTheDocument());
    await user.click(screen.getByText("Create widget installation"));

    await waitFor(() =>
      expect(mockApi.createWidgetInstallation).toHaveBeenCalledWith("tenant-1", { receptionist_id: "receptionist-1" })
    );
    expect(await screen.findByText(/pub-abc123/)).toBeInTheDocument();
  });

  it("never renders the tenant UUID inside the embed snippet", async () => {
    setupDefaultMocks();
    mockApi.listWidgetInstallations.mockResolvedValue([baseInstallation]);
    render(<WidgetInstallationPage />);

    const user = userEvent.setup();
    await user.click(await screen.findByText(/pub-abc123/));

    const snippet = await screen.findByText(/data-receptionist-id="pub-abc123"/);
    expect(snippet.textContent).not.toContain("tenant-1");
  });

  it("saves allowed domains for the selected installation", async () => {
    setupDefaultMocks();
    mockApi.listWidgetInstallations.mockResolvedValue([baseInstallation]);
    const user = userEvent.setup();
    render(<WidgetInstallationPage />);

    await user.click(await screen.findByText(/pub-abc123/));
    const domainsInput = await screen.findByLabelText(/allowed domains/i);
    await user.clear(domainsInput);
    await user.type(domainsInput, "example.com");
    await user.click(screen.getByText("Save allowed domains"));

    await waitFor(() =>
      expect(mockApi.updateWidgetInstallation).toHaveBeenCalledWith("tenant-1", "install-1", {
        allowed_domains: ["example.com"],
      })
    );
  });

  it("activates a draft installation", async () => {
    setupDefaultMocks();
    mockApi.listWidgetInstallations.mockResolvedValue([baseInstallation]);
    const user = userEvent.setup();
    render(<WidgetInstallationPage />);

    await user.click(await screen.findByText(/pub-abc123/));
    await user.click(await screen.findByText("Activate"));

    await waitFor(() => expect(mockApi.activateWidgetInstallation).toHaveBeenCalledWith("tenant-1", "install-1"));
  });

  it("revokes an installation and hides status-change controls afterward", async () => {
    setupDefaultMocks();
    mockApi.listWidgetInstallations.mockResolvedValue([{ ...baseInstallation, status: "active" as const }]);
    const user = userEvent.setup();
    render(<WidgetInstallationPage />);

    await user.click(await screen.findByText(/pub-abc123/));
    await user.click(await screen.findByText("Revoke"));

    await waitFor(() => expect(mockApi.revokeWidgetInstallation).toHaveBeenCalledWith("tenant-1", "install-1"));
    expect(screen.queryByText("Activate")).not.toBeInTheDocument();
  });

  it("displays captured contact and appointment records", async () => {
    setupDefaultMocks();
    mockApi.listWidgetContacts.mockResolvedValue([
      {
        id: "contact-1",
        conversation_id: "conv-1",
        name: "Jane Visitor",
        normalized_email: "jane@example.com",
        normalized_phone: null,
        preferred_contact_method: null,
        marketing_consent: false,
        consent_captured_at: null,
        source: "widget",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockApi.listWidgetAppointmentRequests.mockResolvedValue([
      {
        id: "appt-1",
        conversation_id: "conv-1",
        contact_id: "contact-1",
        receptionist_id: "receptionist-1",
        location_id: null,
        service_id: null,
        requested_date: "2027-01-15",
        requested_time: null,
        requested_time_window: "morning",
        timezone: "UTC",
        notes: null,
        status: "pending" as const,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    render(<WidgetInstallationPage />);

    expect(await screen.findByText("Jane Visitor")).toBeInTheDocument();
    expect(await screen.findByText("jane@example.com")).toBeInTheDocument();
    expect(await screen.findByText("2027-01-15")).toBeInTheDocument();
    expect(await screen.findByText("pending")).toBeInTheDocument();
  });

  it("resolves service and location names in the appointment-requests table", async () => {
    setupDefaultMocks();
    mockApi.listWidgetAppointmentRequests.mockResolvedValue([
      {
        id: "appt-1",
        conversation_id: "conv-1",
        contact_id: null,
        receptionist_id: "receptionist-1",
        location_id: "loc-1",
        service_id: "svc-1",
        requested_date: "2027-01-15",
        requested_time: null,
        requested_time_window: "morning",
        timezone: "UTC",
        notes: null,
        status: "pending" as const,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const phase3Api = await import("@/lib/phase3-api");
    // mockResolvedValueOnce (not mockResolvedValue) deliberately — the
    // component calls each of these exactly once per mount, and
    // afterEach only clears call history, not implementations, so a
    // persistent override here would leak into later tests.
    vi.mocked(phase3Api.listServices).mockResolvedValueOnce([
      { id: "svc-1", tenant_id: "tenant-1", location_id: null, name: "Consultation", description: null, category: null, price_note: null, currency: null, duration_minutes: null, is_active: true, display_order: 0, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
    ]);
    vi.mocked(phase3Api.listLocations).mockResolvedValueOnce([
      { id: "loc-1", tenant_id: "tenant-1", name: "Downtown", address_line: null, city: null, region: null, country: null, postal_code: null, timezone: "UTC", public_phone: null, working_hours: { days: [] }, is_primary: false, is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
    ]);

    render(<WidgetInstallationPage />);

    expect(await screen.findByText("Consultation")).toBeInTheDocument();
    expect(await screen.findByText("Downtown")).toBeInTheDocument();
  });

  describe("live local preview", () => {
    it("shows an activation prompt instead of the iframe for a non-active installation", async () => {
      setupDefaultMocks();
      mockApi.listWidgetInstallations.mockResolvedValue([baseInstallation]); // status: draft
      const user = userEvent.setup();
      render(<WidgetInstallationPage />);

      await user.click(await screen.findByText(/pub-abc123/));

      expect(await screen.findByText(/Activate this installation to preview it live/)).toBeInTheDocument();
      expect(document.querySelector("iframe")).not.toBeInTheDocument();
    });

    it("renders a sandboxed iframe pointing at the real bundle and public config for an active installation", async () => {
      setupDefaultMocks();
      mockApi.listWidgetInstallations.mockResolvedValue([{ ...baseInstallation, status: "active" as const }]);
      const user = userEvent.setup();
      render(<WidgetInstallationPage />);

      await user.click(await screen.findByText(/pub-abc123/));

      const iframe = await screen.findByTitle("Live local widget preview");
      const src = iframe.getAttribute("src") ?? "";
      expect(src).toContain("/widget-preview.html?");
      expect(src).toContain(`publicId=${baseInstallation.public_id}`);
      expect(src).toContain(encodeURIComponent("http://localhost:5174/widget.js"));
      expect(iframe.getAttribute("sandbox")).toBe("allow-scripts allow-same-origin allow-forms");
      expect(await screen.findByText("Live local preview — Mock AI")).toBeInTheDocument();
    });

    it("restarting the preview changes the session namespace in the iframe src", async () => {
      setupDefaultMocks();
      mockApi.listWidgetInstallations.mockResolvedValue([{ ...baseInstallation, status: "active" as const }]);
      const user = userEvent.setup();
      render(<WidgetInstallationPage />);

      await user.click(await screen.findByText(/pub-abc123/));
      const iframeBefore = await screen.findByTitle("Live local widget preview");
      const srcBefore = iframeBefore.getAttribute("src");

      await user.click(await screen.findByText("Restart preview"));

      const iframeAfter = await screen.findByTitle("Live local widget preview");
      expect(iframeAfter.getAttribute("src")).not.toBe(srcBefore);
    });
  });
});
