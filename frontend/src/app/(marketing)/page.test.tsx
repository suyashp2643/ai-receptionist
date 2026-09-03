import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "./page";

describe("HomePage", () => {
  it("renders the hero with a primary and secondary CTA", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/receptionist/i);
    const primary = screen.getAllByRole("link", { name: "Try live demo" })[0];
    expect(primary).toHaveAttribute("href", "/demo");
    const secondary = screen.getByRole("link", { name: "See how it works" });
    expect(secondary).toHaveAttribute("href", "#how-it-works");
  });

  it("discloses the interactive preview is a Mock AI demo", () => {
    render(<HomePage />);
    expect(screen.getByText(/mock ai demo/i)).toBeInTheDocument();
  });

  it("labels the dashboard showcase as sample, not real customer data", () => {
    render(<HomePage />);
    expect(screen.getByText(/sample data — not a real customer/i)).toBeInTheDocument();
  });

  it("marks pricing as a placeholder, not final", () => {
    render(<HomePage />);
    expect(screen.getByText(/placeholder pricing/i)).toBeInTheDocument();
  });

  it("avoids unverifiable superlative marketing language", () => {
    render(<HomePage />);
    const text = document.body.textContent ?? "";
    for (const banned of ["revolutionary", "guaranteed revenue", "replace your entire team", "human-level", "world's best"]) {
      expect(text.toLowerCase()).not.toContain(banned.toLowerCase());
    }
  });
});
