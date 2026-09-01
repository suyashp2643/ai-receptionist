import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { errorMessage } from "@/components/settings/shared";
import { getRequirementsFromError } from "./phase3-api";

describe("ApiError", () => {
  it("carries the status code and message", () => {
    const err = new ApiError(422, "Validation error");
    expect(err.status).toBe(422);
    expect(err.message).toBe("Validation error");
    expect(err.details).toBeNull();
  });

  it("carries structured details when provided", () => {
    const err = new ApiError(422, "Onboarding requirements are not met yet.", {
      requirements: [{ code: "knowledge_or_faq", message: "Add an FAQ.", step: "knowledge" }],
    });
    expect(err.details?.requirements).toHaveLength(1);
  });
});

describe("errorMessage (frontend presentation of a failed request)", () => {
  it("surfaces the ApiError's own message for a known API error", () => {
    const err = new ApiError(409, "Email is already registered.");
    expect(errorMessage(err)).toBe("Email is already registered.");
  });

  it("never leaks a raw non-ApiError exception's internals to the user", () => {
    expect(errorMessage(new TypeError("fetch failed: ECONNREFUSED"))).toBe(
      "Something went wrong. Please try again."
    );
  });

  it("handles a thrown non-Error value gracefully", () => {
    expect(errorMessage("a raw string was thrown")).toBe("Something went wrong. Please try again.");
    expect(errorMessage(undefined)).toBe("Something went wrong. Please try again.");
  });
});

describe("getRequirementsFromError", () => {
  it("extracts the requirements list from a structured 422", () => {
    const err = new ApiError(422, "Onboarding requirements are not met yet.", {
      requirements: [
        { code: "enabled_actions", message: "Enable an action.", step: "actions" },
        { code: "knowledge_or_faq", message: "Add an FAQ.", step: "knowledge" },
      ],
    });
    const requirements = getRequirementsFromError(err);
    expect(requirements).toHaveLength(2);
    expect(requirements[0].code).toBe("enabled_actions");
  });

  it("returns an empty array for an error with no requirements", () => {
    expect(getRequirementsFromError(new ApiError(404, "Not found"))).toEqual([]);
  });

  it("returns an empty array for a non-ApiError value", () => {
    expect(getRequirementsFromError(new Error("boom"))).toEqual([]);
  });
});
