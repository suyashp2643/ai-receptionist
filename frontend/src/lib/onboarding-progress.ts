// Pure helpers for presenting onboarding progress and completion
// requirements — extracted from the components that use them so the logic
// is testable without mounting React.

import type { OnboardingRequirement, OnboardingStepStatus } from "@/lib/phase3-api";

export function countCompletedSteps(steps: Record<string, boolean> | OnboardingStepStatus): number {
  return Object.values(steps).filter(Boolean).length;
}

export interface RequirementsSummary {
  /** True when onboarding has never been completed and requirements block it. */
  isBlocking: boolean;
  /** True when onboarding is already completed but has since regressed. */
  isWarning: boolean;
  requirements: OnboardingRequirement[];
}

/** Single source of truth for the "blocking vs. warning" presentation
 * decision described in docs/PROGRESS.md: once a tenant is `completed`,
 * the exact same incomplete_requirements list is shown as a non-blocking
 * warning rather than something preventing further use. */
export function summarizeRequirements(
  status: "not_started" | "in_progress" | "completed",
  requirements: OnboardingRequirement[]
): RequirementsSummary {
  const hasRequirements = requirements.length > 0;
  return {
    isBlocking: hasRequirements && status !== "completed",
    isWarning: hasRequirements && status === "completed",
    requirements,
  };
}

/** Groups requirements by their target onboarding step, preserving first-seen
 * order — used to render "N steps need attention" rather than one flat list
 * when several requirements point at the same step. */
export function groupRequirementsByStep(
  requirements: OnboardingRequirement[]
): { step: string; items: OnboardingRequirement[] }[] {
  const order: string[] = [];
  const groups = new Map<string, OnboardingRequirement[]>();
  for (const requirement of requirements) {
    if (!groups.has(requirement.step)) {
      groups.set(requirement.step, []);
      order.push(requirement.step);
    }
    groups.get(requirement.step)!.push(requirement);
  }
  return order.map((step) => ({ step, items: groups.get(step)! }));
}
