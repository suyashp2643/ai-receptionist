import type { Metadata } from "next";
import Link from "next/link";
import { Card, Eyebrow, PrimaryButton, Section } from "@/components/marketing/ui";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Industries",
  description: "How AI Receptionist works for clinics, hotels, real estate, and other service businesses.",
  path: "/industries",
});

const INDUSTRIES = [
  { href: "/industries/clinics", title: "Clinics", detail: "Appointment requests, FAQs, and deterministic emergency-language safety handling." },
  { href: "/industries/hotels", title: "Hotels", detail: "Amenities, policies, and reservation requests your front desk confirms." },
  { href: "/industries/real-estate", title: "Real estate", detail: "Buyer qualification, property information, and site-visit requests." },
];

export default function IndustriesPage() {
  return (
    <Section className="pt-16 sm:pt-24">
      <Eyebrow>Industries</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Built for service businesses</h1>
      <p className="mt-4 max-w-2xl text-white/70">
        AI Receptionist applies the same grounded, qualification-driven approach to any service business — the
        pages below show it configured for three common cases. If yours isn&apos;t listed, the same underlying
        capabilities — grounded answers, qualification, appointment requests, handoffs — still apply.
      </p>
      <div className="mt-10 grid gap-6 sm:grid-cols-3">
        {INDUSTRIES.map((ind) => (
          <Link key={ind.href} href={ind.href} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded-2xl">
            <Card className="h-full hover:bg-white/[0.07]">
              <h2 className="font-semibold text-white text-lg">{ind.title}</h2>
              <p className="mt-2 text-sm text-white/60">{ind.detail}</p>
            </Card>
          </Link>
        ))}
      </div>
      <div className="mt-10">
        <PrimaryButton href="/demo">Try a live demo</PrimaryButton>
      </div>
    </Section>
  );
}
