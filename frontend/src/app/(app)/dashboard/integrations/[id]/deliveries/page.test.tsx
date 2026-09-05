import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IntegrationDeliveriesPage from "./page";
import type { IntegrationOutboxEventItem } from "@/lib/integrations-api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "conn-1" }),
  usePathname: () => "/dashboard/integrations/conn-1/deliveries",
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

const mockApi = vi.hoisted(() => ({ listDeliveries: vi.fn(), replayDelivery: vi.fn() }));
vi.mock("@/lib/integrations-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/integrations-api")>();
  return { ...actual, listDeliveries: mockApi.listDeliveries, replayDelivery: mockApi.replayDelivery };
});

function makeDelivery(overrides: Partial<IntegrationOutboxEventItem> = {}): IntegrationOutboxEventItem {
  return {
    id: "evt-1",
    event_type: "enquiry.qualified",
    event_version: 1,
    status: "delivered",
    attempt_count: 1,
    available_at: "2026-01-01T00:00:00Z",
    delivered_at: "2026-01-01T00:01:00Z",
    dead_lettered_at: null,
    last_error: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  membership.role = "owner";
  vi.clearAllMocks();
});

describe("IntegrationDeliveriesPage", () => {
  it("shows an empty state when there are no deliveries", async () => {
    mockApi.listDeliveries.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    render(<IntegrationDeliveriesPage />);
    await waitFor(() => expect(screen.getByText("No deliveries yet")).toBeInTheDocument());
  });

  it("shows an error state on failure", async () => {
    mockApi.listDeliveries.mockRejectedValue(new Error("boom"));
    render(<IntegrationDeliveriesPage />);
    await waitFor(() => expect(screen.getByText("Could not load delivery history.")).toBeInTheDocument());
  });

  it("only shows a Replay action for dead-lettered deliveries, and only for a manager", async () => {
    mockApi.listDeliveries.mockResolvedValue({
      items: [
        makeDelivery({ id: "evt-delivered", status: "delivered" }),
        makeDelivery({ id: "evt-dead", status: "dead_letter", dead_lettered_at: "2026-01-01T00:02:00Z", last_error: "connection refused" }),
      ],
      total: 2,
      limit: 25,
      offset: 0,
    });
    render(<IntegrationDeliveriesPage />);
    await waitFor(() => expect(screen.getAllByRole("row").length).toBeGreaterThan(1));
    expect(screen.getAllByRole("button", { name: "Replay" })).toHaveLength(1);
    expect(screen.getByText("connection refused")).toBeInTheDocument();
  });

  it("hides the Actions column entirely for a member", async () => {
    membership.role = "member";
    mockApi.listDeliveries.mockResolvedValue({
      items: [makeDelivery({ status: "dead_letter" })],
      total: 1,
      limit: 25,
      offset: 0,
    });
    render(<IntegrationDeliveriesPage />);
    await waitFor(() => expect(screen.getByText("enquiry.qualified")).toBeInTheDocument());
    expect(screen.queryByText("Actions")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Replay" })).not.toBeInTheDocument();
  });

  it("replays a dead-lettered delivery and reloads the list", async () => {
    mockApi.listDeliveries
      .mockResolvedValueOnce({ items: [makeDelivery({ id: "evt-dead", status: "dead_letter" })], total: 1, limit: 25, offset: 0 })
      .mockResolvedValueOnce({ items: [makeDelivery({ id: "evt-dead", status: "delivered" })], total: 1, limit: 25, offset: 0 });
    mockApi.replayDelivery.mockResolvedValue(makeDelivery({ id: "evt-dead", status: "delivered" }));
    render(<IntegrationDeliveriesPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Replay" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Replay" }));

    await waitFor(() => expect(mockApi.replayDelivery).toHaveBeenCalledWith("tenant-1", "conn-1", "evt-dead"));
    await waitFor(() => expect(mockApi.listDeliveries).toHaveBeenCalledTimes(2));
  });

  it("shows pagination controls only when there is more than one page", async () => {
    mockApi.listDeliveries.mockResolvedValue({
      items: [makeDelivery()],
      total: 1,
      limit: 25,
      offset: 0,
    });
    render(<IntegrationDeliveriesPage />);
    await waitFor(() => expect(screen.getByText("enquiry.qualified")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
  });
});
