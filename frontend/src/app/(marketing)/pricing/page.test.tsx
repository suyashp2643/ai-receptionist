import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import PricingPage from "./page";
import { pricingPlans } from "@/lib/pricing";

describe("PricingPage", () => {
  it("renders every configured plan from the pricing configuration, not hardcoded", () => {
    render(<PricingPage />);
    for (const plan of pricingPlans) {
      expect(screen.getByRole("heading", { name: plan.name })).toBeInTheDocument();
    }
  });

  it("shows the placeholder-pricing notice", () => {
    render(<PricingPage />);
    expect(screen.getByText(/placeholder pricing/i)).toBeInTheDocument();
  });

  it("has no checkout or payment form — only Contact-us links", () => {
    render(<PricingPage />);
    expect(screen.queryByRole("button", { name: /pay|checkout|subscribe/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Contact us" }).length).toBeGreaterThan(0);
  });

  it("states usage/overage terms are to be finalized", () => {
    render(<PricingPage />);
    expect(screen.getAllByText(/to be finalized/i).length).toBeGreaterThan(0);
  });
});
