/**
 * Interactive demo configuration (Phase 7). `publicId` values here MUST
 * match the fixed public_id each fictional tenant is seeded with — see
 * backend/app/seed_data/public_demo_tenants.py (public_id is not a secret
 * by design; see WidgetInstallation's docstring). Run
 * `.venv/bin/python scripts/seed_public_demos.py` from backend/ before
 * these demos will actually respond — see docs/local-development.md.
 */

export type DemoConfig = {
  slug: "clinic" | "hotel" | "real-estate";
  publicId: string;
  industryLabel: string;
  businessName: string;
  tagline: string;
  suggestedQuestions: string[];
  safetyNote: string;
};

export const demos: DemoConfig[] = [
  {
    slug: "clinic",
    publicId: "demo-clinic-sunrise",
    industryLabel: "Clinic",
    businessName: "Sunrise Family Clinic",
    tagline: "General information, appointment requests, and a real safety response for emergency language.",
    suggestedQuestions: [
      "What services do you offer?",
      "Are you open on Saturday?",
      "I need an appointment tomorrow.",
    ],
    safetyNote:
      "This assistant does not diagnose, prescribe, or replace medical professionals. For any real medical emergency, call your local emergency number.",
  },
  {
    slug: "hotel",
    publicId: "demo-hotel-azurebay",
    industryLabel: "Hotel",
    businessName: "Azure Bay Resort",
    tagline: "Amenities, policies, and reservation requests that a staff member confirms — never guaranteed inventory.",
    suggestedQuestions: [
      "What amenities are included?",
      "Do you have airport pickup?",
      "I'd like to stay for three nights.",
    ],
    safetyNote: "Reservation requests are not confirmed bookings until a staff member follows up.",
  },
  {
    slug: "real-estate",
    publicId: "demo-realestate-falcon",
    industryLabel: "Real estate",
    businessName: "Falcon Heights Realty",
    tagline: "Buyer qualification, property information, and site-visit requests handed off to an agent.",
    suggestedQuestions: ["Show me available two-bedroom properties.", "My budget is AED 2 million.", "Can I schedule a site visit?"],
    safetyNote:
      "This assistant does not verify legal title, give investment guarantees, or replace professional legal or financial advice.",
  },
];

export function getDemoBySlug(slug: string): DemoConfig | undefined {
  return demos.find((d) => d.slug === slug);
}
