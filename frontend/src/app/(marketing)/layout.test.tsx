import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import MarketingLayout from "./layout";

const mockApi = vi.hoisted(() => ({ refreshAccessToken: vi.fn(), apiRequest: vi.fn(), apiRequestWithCsrf: vi.fn() }));
vi.mock("@/lib/api", () => mockApi);

describe("MarketingLayout — no dashboard auth on public pages", () => {
  it("never calls refreshAccessToken (no AuthProvider wraps the public marketing route group)", () => {
    render(
      <MarketingLayout>
        <p>public page content</p>
      </MarketingLayout>
    );
    expect(screen.getByText("public page content")).toBeInTheDocument();
    expect(mockApi.refreshAccessToken).not.toHaveBeenCalled();
    expect(mockApi.apiRequest).not.toHaveBeenCalled();
  });
});
