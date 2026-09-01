// Pure decision function for OnboardingProvider's route guard — extracted so
// the redirect logic (unauthenticated -> /login, no workspace / member role
// -> /dashboard, already-completed tenant -> /dashboard) is testable without
// mounting the provider, mocking next/navigation, or hitting the network.

export interface OnboardingRedirectInput {
  authLoading: boolean;
  hasUser: boolean;
  hasMembership: boolean;
  role: "owner" | "admin" | "member" | null;
  onboardingStatus: "not_started" | "in_progress" | "completed" | null;
}

/** Returns the path to redirect to, or null to stay on the current onboarding page. */
export function computeOnboardingRedirect(input: OnboardingRedirectInput): string | null {
  if (input.authLoading) return null;
  if (!input.hasUser) return "/login";
  if (!input.hasMembership) return "/dashboard";
  if (input.role === "member") return "/dashboard";
  if (input.onboardingStatus === "completed") return "/dashboard";
  return null;
}
