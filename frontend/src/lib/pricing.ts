/**
 * Centralized pricing configuration (Phase 7). Final commercial pricing has
 * not been approved — every price below is an explicitly editable
 * placeholder, never presented as finalized (see the pricing page's own
 * "placeholder pricing" notice). No payment processing exists in Phase 7;
 * this configuration only drives the marketing pricing page's display and
 * feature-comparison table.
 */

export type PricingPlan = {
  id: "starter" | "growth" | "scale";
  name: string;
  monthlyPriceUsd: number | null; // null = "Contact us"
  annualPriceUsd: number | null; // null = "Contact us"
  isPlaceholder: boolean;
  description: string;
  highlighted?: boolean;
  features: string[];
};

export const pricingPlans: PricingPlan[] = [
  {
    id: "starter",
    name: "Starter",
    monthlyPriceUsd: 49,
    annualPriceUsd: 39,
    isPlaceholder: true,
    description: "For a single location getting started with an AI front desk.",
    features: [
      "1 receptionist, 1 widget installation",
      "Grounded answers from your knowledge base and FAQs",
      "Qualification workflow with contact and enquiry capture",
      "Appointment requests and human handoff",
      "Operations dashboard and analytics",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    monthlyPriceUsd: 149,
    annualPriceUsd: 119,
    isPlaceholder: true,
    description: "For growing teams managing multiple locations or receptionists.",
    highlighted: true,
    features: [
      "Everything in Starter",
      "Multiple receptionists and locations",
      "Team roles: owner, admin, member",
      "CSV export for conversations, contacts, enquiries, appointments, handoffs",
      "Priority support",
    ],
  },
  {
    id: "scale",
    name: "Scale",
    monthlyPriceUsd: null,
    annualPriceUsd: null,
    isPlaceholder: true,
    description: "For larger or multi-brand operations with custom needs.",
    features: [
      "Everything in Growth",
      "Custom usage volume — to be finalized",
      "Dedicated onboarding support",
      "Custom retention and security review",
      "Contact us for a tailored quote",
    ],
  },
];

export const pricingFaq: { question: string; answer: string }[] = [
  {
    question: "Is this pricing final?",
    answer:
      "No. The prices shown are clearly marked, editable placeholders pending final commercial approval — not a finalized price list. Contact us for current pricing.",
  },
  {
    question: "How does usage or overage work?",
    answer: "Usage and overage terms are still to be finalized. They will be published here once decided.",
  },
  {
    question: "Is there a setup fee?",
    answer:
      "Implementation and setup details, including whether a setup fee applies, are to be finalized and will depend on plan and configuration complexity.",
  },
  {
    question: "Can I pay monthly or annually?",
    answer: "Both monthly and annual billing are shown above as planned options — no payment processing exists yet.",
  },
];
