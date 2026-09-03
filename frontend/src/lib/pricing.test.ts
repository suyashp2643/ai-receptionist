import { describe, expect, it } from "vitest";
import { pricingFaq, pricingPlans } from "./pricing";

describe("pricingPlans", () => {
  it("has exactly Starter, Growth, and Scale", () => {
    expect(pricingPlans.map((p) => p.id)).toEqual(["starter", "growth", "scale"]);
  });

  it("marks every plan's price as an explicit placeholder", () => {
    for (const plan of pricingPlans) {
      expect(plan.isPlaceholder).toBe(true);
    }
  });

  it("Scale uses Contact-us pricing (null), not a speculative number", () => {
    const scale = pricingPlans.find((p) => p.id === "scale")!;
    expect(scale.monthlyPriceUsd).toBeNull();
    expect(scale.annualPriceUsd).toBeNull();
  });

  it("Starter and Growth have concrete placeholder monthly prices", () => {
    const starter = pricingPlans.find((p) => p.id === "starter")!;
    const growth = pricingPlans.find((p) => p.id === "growth")!;
    expect(typeof starter.monthlyPriceUsd).toBe("number");
    expect(typeof growth.monthlyPriceUsd).toBe("number");
  });
});

describe("pricingFaq", () => {
  it("explicitly addresses that pricing is not final", () => {
    const notFinal = pricingFaq.find((f) => /final/i.test(f.question));
    expect(notFinal).toBeDefined();
    expect(notFinal!.answer).toMatch(/placeholder/i);
  });
});
