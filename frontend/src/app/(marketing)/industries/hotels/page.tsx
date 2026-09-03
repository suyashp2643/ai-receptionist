import type { Metadata } from "next";
import { IndustryPage, type IndustryPageContent } from "@/components/marketing/IndustryPage";
import { buildMetadata } from "@/lib/seo";

const content: IndustryPageContent = {
  slug: "hotels",
  name: "Hotels",
  headline: "Answer amenity and policy questions instantly — confirm reservations your way.",
  subhead:
    "AI Receptionist shares room, amenity, and policy information from your own content, and collects reservation requests for your front desk to confirm. Local recommendations are only offered when they exist in your approved knowledge — never invented.",
  painPoints: [
    "The front desk fields the same amenity and policy questions every day.",
    "After-hours enquiries wait until morning for a reply.",
    "Reservation requests submitted by email or form often miss key details.",
    "Guests expect an instant answer, even outside staffed hours.",
  ],
  workflow: [
    { title: "Visitor asks about rooms or amenities", detail: "Answered from your own content — amenities, policies, and included services." },
    { title: "Availability enquiry", detail: "Enquiries are captured as requests, not confirmed inventory, unless a booking system is integrated." },
    { title: "Reservation request", detail: "Structured details (dates, guests, preferences) are collected for your front desk to confirm." },
    { title: "Staff confirmation or handoff", detail: "Anything needing a person's judgment — special requests, disputes — is handed off." },
  ],
  capabilities: [
    "Grounded answers on rooms, amenities, and policies from your own content",
    "Availability enquiry capture — not confirmed inventory unless a booking system is integrated",
    "Local recommendations only when present in your approved knowledge, never invented",
    "Reservation requests collected for staff confirmation",
    "Human handoff for anything needing staff judgment",
    "Multilingual capability: planned, not yet available — see the note below",
  ],
  safety: [
    "Reservation requests are not confirmed bookings until a staff member follows up — the assistant never tells a visitor their room is booked.",
    "Multilingual support is not yet available; it is a planned capability, not a current one.",
    "Local recommendations are given only when they exist in your own approved knowledge — never fabricated.",
  ],
  demoHref: "/demo/hotel",
  demoLabel: "Try the hotel demo",
  faq: [
    { question: "Can it check real-time room availability?", answer: "Not unless a booking/inventory system is integrated — by default it captures an availability enquiry for staff to confirm, not confirmed inventory." },
    { question: "Does it support multiple languages?", answer: "Not yet — multilingual support is a planned capability, described honestly as planned rather than claimed as available." },
    { question: "Will a guest be told their reservation is confirmed?", answer: "No — reservation requests are explicitly framed as requests a staff member confirms, never a guaranteed booking." },
  ],
};

export const metadata: Metadata = buildMetadata({
  title: "AI Receptionist for Hotels",
  description: "Amenity and policy answers, availability enquiry capture, and reservation requests for hotels.",
  path: "/industries/hotels",
});

export default function HotelsIndustryPage() {
  return <IndustryPage content={content} />;
}
