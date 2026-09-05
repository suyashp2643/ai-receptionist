import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewIntegrationPage from "./page";
import { ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/dashboard/integrations/new",
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

const mockApi = vi.hoisted(() => ({ createIntegration: vi.fn() }));
vi.mock("@/lib/integrations-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/integrations-api")>();
  return { ...actual, createIntegration: mockApi.createIntegration };
});

afterEach(() => {
  membership.role = "owner";
  vi.clearAllMocks();
});

describe("NewIntegrationPage", () => {
  it("tells a member they cannot create an integration, and never renders the form", () => {
    membership.role = "member";
    render(<NewIntegrationPage />);
    expect(screen.getByText(/Only an owner or admin can create an integration/)).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("defaults to the zero-network mock connector and hides destination/secret fields", () => {
    render(<NewIntegrationPage />);
    expect(screen.getByLabelText("Connector type")).toHaveValue("mock");
    expect(screen.queryByLabelText("Destination URL")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Signing secret")).not.toBeInTheDocument();
    expect(screen.getByText(/zero-network/)).toBeInTheDocument();
  });

  it("shows destination URL and signing secret fields for a webhook connector", async () => {
    render(<NewIntegrationPage />);
    await userEvent.selectOptions(screen.getByLabelText("Connector type"), "webhook");
    expect(screen.getByLabelText("Destination URL")).toBeInTheDocument();
    expect(screen.getByLabelText("Signing secret")).toBeInTheDocument();
  });

  it("shows a PII consent warning next to every event type that carries contact details", () => {
    render(<NewIntegrationPage />);
    const warnings = screen.getAllByText(/Only enable this if your receiver is authorized to handle personal data/);
    // contact.captured, enquiry.created, enquiry.qualified, appointment_request.created, human_handoff.requested
    expect(warnings.length).toBe(5);
  });

  it("never offers safety.escalation_detected for an AI Sales Employee connector", async () => {
    render(<NewIntegrationPage />);
    await userEvent.selectOptions(screen.getByLabelText("Connector type"), "sales_employee");
    expect(screen.queryByText("safety.escalation_detected")).not.toBeInTheDocument();
    expect(screen.getByText(/Safety-related events can never be enabled on this connector type/)).toBeInTheDocument();
  });

  it("drops a previously-checked event when switching to a connector type that disallows it", async () => {
    render(<NewIntegrationPage />);
    const safetyCheckbox = screen.getByRole("checkbox", { name: /safety.escalation_detected/ });
    await userEvent.click(safetyCheckbox);
    expect(safetyCheckbox).toBeChecked();

    await userEvent.selectOptions(screen.getByLabelText("Connector type"), "sales_employee");
    await userEvent.selectOptions(screen.getByLabelText("Connector type"), "mock");

    expect(screen.getByRole("checkbox", { name: /safety.escalation_detected/ })).not.toBeChecked();
  });

  it("submits the form and redirects to the created integration's detail page", async () => {
    mockApi.createIntegration.mockResolvedValue({ id: "new-conn-1" });
    render(<NewIntegrationPage />);

    await userEvent.type(screen.getByLabelText("Name"), "Revenue Brain (production)");
    await userEvent.click(screen.getByRole("checkbox", { name: /enquiry\.qualified/ }));
    await userEvent.click(screen.getByRole("button", { name: "Create integration" }));

    await waitFor(() => expect(mockApi.createIntegration).toHaveBeenCalledTimes(1));
    const [tenantId, payload] = mockApi.createIntegration.mock.calls[0];
    expect(tenantId).toBe("tenant-1");
    expect(payload.connector_type).toBe("mock");
    expect(payload.name).toBe("Revenue Brain (production)");
    expect(payload.enabled_event_types).toEqual(["enquiry.qualified"]);
    expect(payload.signing_secret).toBeNull();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard/integrations/new-conn-1"));
  });

  it("shows the backend's validation error inline (e.g. a rejected destination address) and does not navigate away", async () => {
    mockApi.createIntegration.mockRejectedValue(
      new ApiError(422, "Destination resolves to an address that is not permitted (loopback/link-local/private/reserved/multicast/unspecified).")
    );
    render(<NewIntegrationPage />);

    await userEvent.selectOptions(screen.getByLabelText("Connector type"), "webhook");
    await userEvent.type(screen.getByLabelText("Name"), "QA Webhook");
    await userEvent.type(screen.getByLabelText("Destination URL"), "https://127.0.0.1:9999/hook");
    await userEvent.type(screen.getByLabelText("Signing secret"), "a-shared-secret");
    await userEvent.click(screen.getByRole("button", { name: "Create integration" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/not permitted/));
    expect(push).not.toHaveBeenCalled();
  });

  it("disables submit until a name is entered", () => {
    render(<NewIntegrationPage />);
    expect(screen.getByRole("button", { name: "Create integration" })).toBeDisabled();
  });
});
