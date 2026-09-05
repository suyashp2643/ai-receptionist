import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth } from "./auth-context";

const mockApi = vi.hoisted(() => ({
  refreshAccessToken: vi.fn(),
  apiRequest: vi.fn(),
  apiRequestWithCsrf: vi.fn(),
  setAccessToken: vi.fn(),
}));
vi.mock("@/lib/api", () => mockApi);

function Probe() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <p>loading</p>;
  if (!user) return <p>unauthenticated</p>;
  return <p>authenticated as {user.display_name}</p>;
}

const user = {
  id: "u1",
  normalized_email: "owner@example.com",
  display_name: "Owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
};
const memberships = [{ tenant_id: "t1", tenant_name: "Acme", tenant_slug: "acme", role: "owner" as const, status: "active" }];

afterEach(() => {
  vi.clearAllMocks();
});

describe("AuthProvider — session restoration on mount (e.g. after a full page reload)", () => {
  it("restores an authenticated session when the refresh cookie is still valid", async () => {
    mockApi.refreshAccessToken.mockResolvedValue(true);
    mockApi.apiRequest.mockResolvedValue({ user, memberships });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(screen.getByText("loading")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("authenticated as Owner")).toBeInTheDocument());
    expect(mockApi.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(mockApi.apiRequest).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("resolves to unauthenticated, without redirect-looping, when the refresh cookie is absent/expired/revoked", async () => {
    mockApi.refreshAccessToken.mockResolvedValue(false);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByText("unauthenticated")).toBeInTheDocument());
    // /auth/me is never called once refresh has already failed.
    expect(mockApi.apiRequest).not.toHaveBeenCalled();
  });

  it("resolves to unauthenticated if refresh succeeds but /auth/me then fails", async () => {
    mockApi.refreshAccessToken.mockResolvedValue(true);
    mockApi.apiRequest.mockRejectedValue(new Error("network error"));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByText("unauthenticated")).toBeInTheDocument());
  });

  it("never leaves isLoading true forever — always settles to authenticated or unauthenticated", async () => {
    mockApi.refreshAccessToken.mockResolvedValue(false);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.queryByText("loading")).not.toBeInTheDocument());
  });
});
