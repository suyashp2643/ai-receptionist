import { describe, expect, it } from "vitest";
import { demos, getDemoBySlug } from "./demos";

describe("demos config", () => {
  it("has exactly clinic, hotel, and real-estate", () => {
    expect(demos.map((d) => d.slug)).toEqual(["clinic", "hotel", "real-estate"]);
  });

  it("every demo has a distinct publicId (matching backend's fixed seed values)", () => {
    const ids = demos.map((d) => d.publicId);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(["demo-clinic-sunrise", "demo-hotel-azurebay", "demo-realestate-falcon"]);
  });

  it("every demo has its own distinct suggested questions and safety note", () => {
    const questionSets = demos.map((d) => d.suggestedQuestions.join("|"));
    const safetyNotes = demos.map((d) => d.safetyNote);
    expect(new Set(questionSets).size).toBe(demos.length);
    expect(new Set(safetyNotes).size).toBe(demos.length);
  });

  it("getDemoBySlug resolves a known slug and returns undefined for an unknown one", () => {
    expect(getDemoBySlug("clinic")?.businessName).toBe("Sunrise Family Clinic");
    expect(getDemoBySlug("not-a-real-demo")).toBeUndefined();
  });
});
