import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ClinicsIndustryPage from "./page";

describe("ClinicsIndustryPage", () => {
  it("explicitly states it does not diagnose, prescribe, or replace a medical professional", () => {
    render(<ClinicsIndustryPage />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/does not diagnose, prescribe, or replace a medical professional/i);
  });

  it("describes the deterministic, non-model emergency safety response", () => {
    render(<ClinicsIndustryPage />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/fixed, deterministic response/i);
    expect(text).toMatch(/emergency services/i);
  });

  it("frames appointment requests as requests, never guaranteed bookings", () => {
    render(<ClinicsIndustryPage />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/never (a )?guaranteed booking/i);
  });

  it("links to the clinic demo", () => {
    render(<ClinicsIndustryPage />);
    const links = screen.getAllByRole("link", { name: "Try the clinic demo" });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("href", "/demo/clinic");
  });
});
