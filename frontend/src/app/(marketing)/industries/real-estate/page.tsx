import type { Metadata } from "next";
import { IndustryPage, type IndustryPageContent } from "@/components/marketing/IndustryPage";
import { buildMetadata } from "@/lib/seo";

const content: IndustryPageContent = {
  slug: "real-estate",
  name: "Real estate",
  headline: "Qualify buyers and capture site-visit requests — while you're with another client.",
  subhead:
    "AI Receptionist shares property information from your own listings, captures budget, location, and preference details, and collects site-visit requests for an agent to follow up on. It never verifies legal title or gives investment guarantees.",
  painPoints: [
    "Agents can't answer every inbound enquiry while showing another property.",
    "Unqualified leads consume agent time before budget or intent is known.",
    "Site-visit requests submitted online often lack the details an agent needs.",
    "After-hours enquiries from a listing page go unanswered until the next day.",
  ],
  workflow: [
    { title: "Visitor asks about a property", detail: "Answered from your own listing information — never invented details." },
    { title: "Buyer qualification", detail: "Budget, location, and property-type preferences are captured through a short, configurable set of questions." },
    { title: "Site-visit request", detail: "A structured request is collected — not a confirmed appointment — for an agent to follow up on." },
    { title: "Agent handoff", detail: "The visitor can ask for an agent directly at any point in the conversation." },
  ],
  capabilities: [
    "Grounded property and project information from your own listings",
    "Buyer qualification — budget, location, and property-type preferences",
    "Site-visit requests collected for agent follow-up, never a confirmed appointment",
    "Agent handoff on request",
    "Honest 'I don't know' when a question isn't covered by your listing information",
  ],
  safety: [
    "This assistant does not verify legal title, ownership, or any legal status of a property.",
    "It does not give investment guarantees or predict returns.",
    "It does not replace professional legal, financial, or real estate advice.",
    "A site-visit request is a request only — an agent confirms timing, never the assistant.",
  ],
  demoHref: "/demo/real-estate",
  demoLabel: "Try the real estate demo",
  faq: [
    { question: "Can it tell me if a property's title is clear?", answer: "No — it never verifies legal title or ownership status. That requires a licensed professional." },
    { question: "Will it guarantee a return on investment?", answer: "No. It never gives investment guarantees or predicts returns — it shares only the property information you've provided." },
    { question: "What happens when a visitor asks something not in your listings?", answer: "It gives an honest 'I don't have that information' response rather than inventing an answer, and can offer to hand off to an agent." },
  ],
};

export const metadata: Metadata = buildMetadata({
  title: "AI Receptionist for Real Estate",
  description: "Buyer qualification, property information, and site-visit requests for real estate agencies.",
  path: "/industries/real-estate",
});

export default function RealEstateIndustryPage() {
  return <IndustryPage content={content} />;
}
