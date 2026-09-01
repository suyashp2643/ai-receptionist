import { describe, expect, it } from "vitest";
import { countCompletedSteps, groupRequirementsByStep, summarizeRequirements } from "./onboarding-progress";
import type { OnboardingRequirement } from "./phase3-api";

describe("countCompletedSteps", () => {
  it("counts true values", () => {
    expect(countCompletedSteps({ a: true, b: false, c: true })).toBe(2);
  });

  it("returns 0 for an all-false record", () => {
    expect(countCompletedSteps({ a: false, b: false })).toBe(0);
  });

  it("returns 0 for an empty record", () => {
    expect(countCompletedSteps({})).toBe(0);
  });
});

const requirement = (code: string, step: string): OnboardingRequirement => ({
  code,
  message: `Fix ${code}`,
  step,
});

describe("summarizeRequirements", () => {
  it("is not blocking or warning when there are no requirements", () => {
    const summary = summarizeRequirements("not_started", []);
    expect(summary.isBlocking).toBe(false);
    expect(summary.isWarning).toBe(false);
  });

  it("is blocking when not yet completed and requirements exist", () => {
    const summary = summarizeRequirements("in_progress", [requirement("business_profile", "business")]);
    expect(summary.isBlocking).toBe(true);
    expect(summary.isWarning).toBe(false);
  });

  it("is a warning (not blocking) once already completed", () => {
    const summary = summarizeRequirements("completed", [requirement("knowledge_or_faq", "knowledge")]);
    expect(summary.isBlocking).toBe(false);
    expect(summary.isWarning).toBe(true);
  });

  it("preserves the requirements list unchanged", () => {
    const reqs = [requirement("enabled_actions", "actions")];
    expect(summarizeRequirements("in_progress", reqs).requirements).toBe(reqs);
  });
});

describe("groupRequirementsByStep", () => {
  it("groups multiple requirements pointing at the same step", () => {
    const grouped = groupRequirementsByStep([
      requirement("receptionist_named", "receptionist"),
      requirement("workflow_active", "receptionist"),
      requirement("knowledge_or_faq", "knowledge"),
    ]);
    expect(grouped).toHaveLength(2);
    expect(grouped[0].step).toBe("receptionist");
    expect(grouped[0].items).toHaveLength(2);
    expect(grouped[1].step).toBe("knowledge");
    expect(grouped[1].items).toHaveLength(1);
  });

  it("preserves first-seen step order", () => {
    const grouped = groupRequirementsByStep([
      requirement("a", "actions"),
      requirement("b", "business"),
      requirement("c", "actions"),
    ]);
    expect(grouped.map((g) => g.step)).toEqual(["actions", "business"]);
  });

  it("returns an empty array for no requirements", () => {
    expect(groupRequirementsByStep([])).toEqual([]);
  });
});
