/**
 * Centralized branding configuration (Phase 7). The final brand name has
 * not been selected — every public-facing page must read the product name,
 * tagline, and related copy from here, never hardcode it inline. Renaming
 * the product later means editing this one file.
 *
 * "AI Receptionist" below is a professional placeholder name, not a final
 * decision — see docs/PROGRESS.md's Phase 7 section for how to change it.
 */

export const brand = {
  productName: "AI Receptionist",
  shortName: "AI Receptionist",
  tagline: "A receptionist that never misses a conversation.",
  description:
    "AI Receptionist answers visitor questions, qualifies leads, and captures enquiries, appointment requests, and handoffs for clinics, hotels, real estate agencies, and other service businesses — around the clock, grounded in the business's own information.",
  legalName: "AI Receptionist",
  supportEmail: "hello@example.com",
  social: {
    twitter: "",
    linkedin: "",
  },
  cta: {
    primary: "Try live demo",
    secondary: "See how it works",
    contact: "Contact us",
    getStarted: "Get started",
  },
  metadata: {
    titleTemplate: (title: string) => `${title} | AI Receptionist`,
    defaultTitle: "AI Receptionist — Grounded AI front desk for service businesses",
    defaultDescription:
      "A grounded, tenant-safe AI receptionist for clinics, hotels, and real estate — qualifies visitors, captures enquiries and appointment requests, and hands off to your staff. Try an interactive mock-AI demo.",
    ogImageAlt: "AI Receptionist — grounded AI front desk for service businesses",
  },
} as const;

export type Brand = typeof brand;
