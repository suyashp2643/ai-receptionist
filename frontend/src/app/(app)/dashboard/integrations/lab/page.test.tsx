import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IntegrationLabPage from "./page";
import type { IntegrationConnection, IntegrationOutboxEventItem } from "@/lib/integrations-api";

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
  createIntegration: vi.fn(),
  generateInboundApiKey: vi.fn(),
  getIntegration: vi.fn(),
  listDeliveries: vi.fn(),
  processPendingNow: vi.fn(),
  replayDelivery: vi.fn(),
  rotateSigningSecret: vi.fn(),
  sendTestEvent: vi.fn(),
  updateIntegration: vi.fn(),
}));
vi.mock("@/lib/integrations-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/integrations-api")>();
  return { ...actual, ...mockApi };
});

function conn(id: string, overrides: Partial<IntegrationConnection> = {}): IntegrationConnection {
  return {
    id,
    connector_type: "mock",
    name: id,
    status: "configured",
    config: { mode: "success" },
    enabled_event_types: [],
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

function delivery(overrides: Partial<IntegrationOutboxEventItem> = {}): IntegrationOutboxEventItem {
  return {
    id: "evt-1",
    event_type: "connection.test_event",
    event_version: 1,
    status: "delivered",
    attempt_count: 1,
    available_at: "2026-01-01T00:00:00Z",
    delivered_at: "2026-01-01T00:00:01Z",
    dead_lettered_at: null,
    last_error: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ status: 200, json: async () => ({ status: "processed" }) }) as unknown as Response)
  );
});

afterEach(() => {
  membership.role = "owner";
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("IntegrationLabPage", () => {
  it("tells a member they cannot run the lab, and never shows the Run button", () => {
    membership.role = "member";
    render(<IntegrationLabPage />);
    expect(screen.getByText(/Only an owner or admin can run the integration lab/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run the lab" })).not.toBeInTheDocument();
  });

  it("states up front that this is a local, zero-network simulation that sends nothing real", () => {
    render(<IntegrationLabPage />);
    expect(screen.getByText("Local deterministic simulation only")).toBeInTheDocument();
    expect(screen.getByText(/No external service is contacted/)).toBeInTheDocument();
    expect(screen.getByText(/No message, email, WhatsApp, or call is ever sent/)).toBeInTheDocument();
    expect(screen.getByText(/No paid AI provider is used/)).toBeInTheDocument();
    expect(screen.getByText(/All names, leads, and payloads shown below are fictional/)).toBeInTheDocument();
  });

  it("lists all 13 steps in an idle state before running, marking step 11 as test-only", () => {
    render(<IntegrationLabPage />);
    expect(screen.getByText(/1\. Set up three fictional lab connections/)).toBeInTheDocument();
    expect(screen.getByText(/13\. A rotated signing secret invalidates the old signature/)).toBeInTheDocument();
    expect(screen.getByText("proven by automated tests, not live-demonstrated here")).toBeInTheDocument();
  });

  it("runs the full lab end to end and marks every live step green", async () => {
    const revenueBrain = conn("rb-1", { name: "Lab: Revenue Brain" });
    const salesEmployee = conn("se-1", { name: "Lab: AI Sales Employee" });
    const webhook = conn("wh-1", { name: "Lab: Generic Webhook" });
    const failing = conn("fail-1", { name: "Lab: Retryable Failure" });
    const permanentFailure = conn("perm-1", { name: "Lab: Permanent Failure" });

    mockApi.createIntegration
      .mockResolvedValueOnce(revenueBrain)
      .mockResolvedValueOnce(salesEmployee)
      .mockResolvedValueOnce(webhook)
      .mockResolvedValueOnce(failing)
      .mockResolvedValueOnce(permanentFailure);

    mockApi.sendTestEvent.mockResolvedValue(delivery());

    mockApi.processPendingNow
      .mockResolvedValueOnce({ claimed: 1, delivered: 1, retried: 0, dead_lettered: 0 }) // step2 revenueBrain
      .mockResolvedValueOnce({ claimed: 1, delivered: 1, retried: 0, dead_lettered: 0 }) // step4 salesEmployee
      .mockResolvedValueOnce({ claimed: 1, delivered: 1, retried: 0, dead_lettered: 0 }) // step5 webhook
      .mockResolvedValueOnce({ claimed: 1, delivered: 0, retried: 1, dead_lettered: 0 }) // step6 failing
      .mockResolvedValueOnce({ claimed: 1, delivered: 0, retried: 0, dead_lettered: 1 }) // step7 permanentFailure
      .mockResolvedValueOnce({ claimed: 1, delivered: 1, retried: 0, dead_lettered: 0 }); // step8 replay redelivery

    mockApi.listDeliveries
      .mockResolvedValueOnce({ items: [delivery({ status: "delivered" })], total: 1, limit: 1, offset: 0 }) // step2
      .mockResolvedValueOnce({ items: [delivery({ status: "delivered" })], total: 1, limit: 1, offset: 0 }) // step5
      .mockResolvedValueOnce({ items: [delivery({ status: "pending", attempt_count: 1 })], total: 1, limit: 1, offset: 0 }) // step6
      .mockResolvedValueOnce({ items: [delivery({ id: "dead-evt", status: "dead_letter" })], total: 1, limit: 1, offset: 0 }); // step8 deliveriesForReplay

    mockApi.generateInboundApiKey
      .mockResolvedValueOnce({ api_key: "airk_first", prefix: "airk_", last_four: "irst" }) // step3
      .mockResolvedValueOnce({ api_key: "airk_rotated", prefix: "airk_", last_four: "ated" }); // step11

    mockApi.getIntegration
      .mockResolvedValueOnce(conn("perm-1", { version: 2 })) // step8 freshDetail
      .mockResolvedValueOnce(conn("rb-1", { version: 3 })) // step11 freshBeforeRotateKey
      .mockResolvedValueOnce(conn("rb-1", { version: 4 })); // step12 freshBeforeRotateSecret

    mockApi.updateIntegration.mockResolvedValue(conn("perm-1", { version: 3, config: { mode: "success" } }));
    mockApi.replayDelivery.mockResolvedValue(delivery({ id: "dead-evt", status: "delivered" }));
    mockApi.rotateSigningSecret.mockResolvedValue(conn("rb-1", { version: 5 }));

    // Calls in order: step3 (priority event, new key/secret) -> 200,
    // step9 (duplicate replay of the same request) -> 200 "duplicate",
    // step11 (retry with the now-rotated-away-from key) -> 401,
    // step12 (old secret) -> 401, step12 (new secret) -> 200.
    const fetchResponses = [
      { status: 200, json: async () => ({ status: "processed" }) },
      { status: 200, json: async () => ({ status: "duplicate" }) },
      { status: 401, json: async () => ({ error: "invalid api key" }) },
      { status: 401, json: async () => ({ error: "invalid signature" }) },
      { status: 200, json: async () => ({ status: "processed" }) },
    ];
    let fetchCallIndex = 0;
    const fetchMock = vi.fn(async () => fetchResponses[fetchCallIndex++] as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<IntegrationLabPage />);
    await userEvent.click(screen.getByRole("button", { name: "Run the lab" }));

    await waitFor(
      () =>
        expect(
          screen.getByText(/13\. A rotated signing secret invalidates the old signature/).closest("li")
        ).toHaveTextContent("✅"),
      { timeout: 10000 }
    );

    expect(mockApi.createIntegration).toHaveBeenCalledTimes(5);
    expect(mockApi.sendTestEvent).toHaveBeenCalledTimes(5);
    // No step should report a failure icon.
    expect(screen.queryByText("❌")).not.toBeInTheDocument();
  }, 15000);

  it("reports a setup failure inline and does not crash when the backend rejects connection creation", async () => {
    mockApi.createIntegration.mockRejectedValue(new Error("Could not reach the backend."));
    render(<IntegrationLabPage />);
    await userEvent.click(screen.getByRole("button", { name: "Run the lab" }));

    await waitFor(() =>
      expect(screen.getByText(/1\. Set up three fictional lab connections/).closest("li")).toHaveTextContent(
        "Could not reach the backend."
      )
    );
    expect(screen.getByRole("button", { name: "Run the lab" })).toBeEnabled();
  });
});
