import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ClinicDemoPage from "./page";
import { getDemoBySlug } from "@/lib/demos";

describe("ClinicDemoPage", () => {
  it("discloses this is a Mock AI demo", () => {
    render(<ClinicDemoPage />);
    expect(screen.getByText(/mock ai demo/i)).toBeInTheDocument();
  });

  it("shows the demo's own suggested questions", () => {
    render(<ClinicDemoPage />);
    const demo = getDemoBySlug("clinic")!;
    for (const q of demo.suggestedQuestions) {
      expect(screen.getByText(q)).toBeInTheDocument();
    }
  });

  it("shows the demo's own safety note", () => {
    render(<ClinicDemoPage />);
    const demo = getDemoBySlug("clinic")!;
    expect(screen.getByText(demo.safetyNote)).toBeInTheDocument();
  });

  it("mounts an interactive demo iframe for this demo's publicId", async () => {
    render(<ClinicDemoPage />);
    const iframe = await screen.findByTitle("Sunrise Family Clinic interactive demo");
    expect(iframe.getAttribute("src") ?? "").toContain("publicId=demo-clinic-sunrise");
  });
});
