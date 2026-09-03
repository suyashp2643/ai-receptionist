import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { Header } from "./Header";
import { Footer } from "./Footer";
import { ContactForm } from "./ContactForm";
import HomePage from "@/app/(marketing)/page";
import ClinicsIndustryPage from "@/app/(marketing)/industries/clinics/page";
import PricingPage from "@/app/(marketing)/pricing/page";

/** Zero-cost, local automated accessibility checks (axe-core via
 * vitest-axe) on the public site's critical shared components and pages.
 * This is a useful automated baseline, not a claim of full WCAG
 * certification — see docs/security.md / docs/PROGRESS.md's Phase 7
 * accessibility-scope note.
 *
 * Asserts on `violations` directly (rather than vitest-axe's
 * `toHaveNoViolations()` custom matcher) — the matcher's ambient type
 * augmentation didn't resolve cleanly against this project's `tsc
 * --noEmit`, and a plain array assertion is equally rigorous with no
 * typing fragility: a failure prints exactly which rule and node. */
async function expectNoViolations(container: Element) {
  const results = await axe(container);
  if (results.violations.length > 0) {
    const summary = results.violations
      .map((v) => `- ${v.id}: ${v.help} (${v.nodes.length} node(s))`)
      .join("\n");
    throw new Error(`Accessibility violations found:\n${summary}`);
  }
  expect(results.violations).toEqual([]);
}

describe("accessibility (axe)", () => {
  it("Header has no detectable violations", async () => {
    const { container } = render(<Header />);
    await expectNoViolations(container);
  });

  it("Footer has no detectable violations", async () => {
    const { container } = render(<Footer />);
    await expectNoViolations(container);
  });

  it("ContactForm has no detectable violations", async () => {
    const { container } = render(<ContactForm />);
    await expectNoViolations(container);
  });

  it("HomePage has no detectable violations", async () => {
    const { container } = render(<HomePage />);
    // axe-core's iframe cross-frame postMessage check has no jsdom
    // equivalent to talk to (jsdom's <iframe> has no real nested
    // browsing context) and throws rather than skipping — removing the
    // demo-widget iframe node itself (its own document is scanned by its
    // own tests) avoids that unrelated crash without weakening the check
    // on everything else on the page.
    container.querySelectorAll("iframe").forEach((el) => el.remove());
    await expectNoViolations(container);
  });

  it("an industry page has no detectable violations", async () => {
    const { container } = render(<ClinicsIndustryPage />);
    await expectNoViolations(container);
  });

  it("the pricing page has no detectable violations", async () => {
    const { container } = render(<PricingPage />);
    await expectNoViolations(container);
  });
});
