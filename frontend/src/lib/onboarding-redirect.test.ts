import { describe, expect, it } from "vitest";
import { computeOnboardingRedirect } from "./onboarding-redirect";

const base = {
  authLoading: false,
  hasUser: true,
  hasMembership: true,
  role: "owner" as const,
  onboardingStatus: "in_progress" as const,
};

describe("computeOnboardingRedirect", () => {
  it("stays put while auth is still loading, even with no user yet", () => {
    expect(computeOnboardingRedirect({ ...base, authLoading: true, hasUser: false })).toBeNull();
  });

  it("redirects to /login when there is no authenticated user", () => {
    expect(computeOnboardingRedirect({ ...base, hasUser: false })).toBe("/login");
  });

  it("redirects to /dashboard when the user has no workspace", () => {
    expect(computeOnboardingRedirect({ ...base, hasMembership: false })).toBe("/dashboard");
  });

  it("redirects a member (read-only role) to /dashboard", () => {
    expect(computeOnboardingRedirect({ ...base, role: "member" })).toBe("/dashboard");
  });

  it("redirects to /dashboard once onboarding is already completed", () => {
    expect(computeOnboardingRedirect({ ...base, onboardingStatus: "completed" })).toBe("/dashboard");
  });

  it("stays on the onboarding page for an owner with in-progress onboarding", () => {
    expect(computeOnboardingRedirect(base)).toBeNull();
  });

  it("stays on the onboarding page for an admin with not-started onboarding", () => {
    expect(computeOnboardingRedirect({ ...base, role: "admin", onboardingStatus: "not_started" })).toBeNull();
  });
});
