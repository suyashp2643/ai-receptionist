import type { Metadata } from "next";
import Link from "next/link";
import { DemoWidgetEmbed } from "@/components/marketing/DemoWidgetEmbed";
import { Card, Eyebrow, MockAiBadge, PrimaryButton, Section, SecondaryButton } from "@/components/marketing/ui";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { SimpleBarChart } from "@/components/dashboard/SimpleBarChart";
import { brand } from "@/lib/brand";
import { pricingPlans } from "@/lib/pricing";
import { buildMetadata, faqJsonLd, organizationJsonLd } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: brand.metadata.defaultTitle,
  description: brand.metadata.defaultDescription,
  path: "/",
});

const VALUE_STRIP = [
  { label: "24/7 responses", detail: "Answers visitor questions any time, grounded in your own information." },
  { label: "Lead qualification", detail: "Asks the questions your team needs before a lead reaches a person." },
  { label: "Enquiry capture", detail: "Structured contact and enquiry records, not a buried chat transcript." },
  { label: "Appointment requests", detail: "Collects requests for your staff to confirm — never a guaranteed booking." },
  { label: "Human handoff", detail: "Escalates to your team when a conversation needs a person." },
  { label: "Tenant-safe operations", detail: "Every business's data, conversations, and widget are isolated from every other." },
];

const HOW_IT_WORKS = [
  { step: "1", title: "Configure business knowledge", detail: "Add services, FAQs, and knowledge documents your receptionist can ground answers in." },
  { step: "2", title: "Install the widget", detail: "Embed one script tag on your site — no server to run, no separate app to maintain." },
  { step: "3", title: "AI handles and qualifies conversations", detail: "Visitors get grounded answers; qualification questions capture what your team needs." },
  { step: "4", title: "Staff manage outcomes in the dashboard", detail: "Conversations, contacts, enquiries, appointment requests, and handoffs — all in one place." },
];

const INDUSTRY_CARDS = [
  { href: "/industries/clinics", title: "Clinics", detail: "Appointment requests, FAQs, and deterministic emergency-language safety handling." },
  { href: "/industries/hotels", title: "Hotels", detail: "Amenities, policies, and reservation requests your front desk confirms." },
  { href: "/industries/real-estate", title: "Real estate", detail: "Buyer qualification, property information, and site-visit requests." },
  { href: "/industries", title: "Other service businesses", detail: "The same grounded, qualification-driven approach for any service business." },
];

const CAPABILITIES = [
  { title: "Grounded answers with citations", detail: "Answers are retrieved from your own FAQs and knowledge documents, not invented." },
  { title: "Qualification workflows", detail: "Configurable fields capture exactly what your team needs from a visitor." },
  { title: "Contact & enquiry capture", detail: "Structured records, with consent tracked separately from contact details." },
  { title: "Appointment requests", detail: "Collected for staff review — clearly labeled as requests, not confirmed bookings." },
  { title: "Human handoffs", detail: "One-click staff claim and resolve, with an audit trail." },
  { title: "Analytics & operations dashboard", detail: "Tenant-scoped KPIs, conversation lists, and CSV export." },
  { title: "Browser voice where supported", detail: "Optional speech input/output using the visitor's own browser — no added cost." },
  { title: "Safety handling", detail: "Deterministic, non-model safety rules run before any AI-generated response." },
];

const FAQ_ITEMS = [
  { question: "Is this a real AI model?", answer: "The public demos and this site's interactive preview run on a deterministic Mock AI — a rule-based engine, not a live external model — so behavior is reproducible and free to demonstrate. A live deployment can be configured with a real provider." },
  { question: "What happens to a visitor's contact details?", answer: "Contact capture is tenant-scoped and access-controlled; consent to be contacted is tracked as its own field, separate from marketing consent." },
  { question: "Does an appointment request mean it's booked?", answer: "No — appointment and reservation requests are collected for staff to confirm, never presented to a visitor as a guaranteed booking." },
  { question: "Can it handle a medical or legal question?", answer: "No. Clinic and legal safety rules are deterministic and run outside the AI model — the assistant redirects to a professional rather than answering." },
];

export default function HomePage() {
  return (
    <>
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd()) }}
      />
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd(FAQ_ITEMS)) }}
      />

      {/* 1. Hero */}
      <Section className="pt-16 sm:pt-24">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <Eyebrow>AI front desk for service businesses</Eyebrow>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
              A receptionist that never misses a conversation.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-white/70">
              {brand.productName} answers visitor questions, qualifies leads, and captures enquiries, appointment
              requests, and handoffs — grounded in your own business information, for clinics, hotels, real estate,
              and other service businesses.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              <PrimaryButton href="/demo">{brand.cta.primary}</PrimaryButton>
              <SecondaryButton href="#how-it-works">{brand.cta.secondary}</SecondaryButton>
            </div>
          </div>
          <div className="flex flex-col gap-3">
            <MockAiBadge />
            <DemoWidgetEmbed publicId="demo-clinic-sunrise" title="Interactive product preview — clinic demo" height={480} />
          </div>
        </div>
      </Section>

      {/* 2. Trust / value strip */}
      <Section className="border-t border-white/10" ariaLabel="What it handles">
        <h2 className="sr-only">What it handles</h2>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {VALUE_STRIP.map((item) => (
            <Card key={item.label}>
              <h3 className="font-semibold text-white">{item.label}</h3>
              <p className="mt-2 text-sm text-white/60">{item.detail}</p>
            </Card>
          ))}
        </div>
      </Section>

      {/* 3. How it works */}
      <Section id="how-it-works" className="border-t border-white/10" ariaLabel="How it works">
        <Eyebrow>How it works</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">From setup to a handled conversation</h2>
        <ol className="mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {HOW_IT_WORKS.map((item) => (
            <li key={item.step} className="flex flex-col gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-mark-violet-500/20 text-sm font-semibold text-mark-violet-300">
                {item.step}
              </span>
              <h3 className="font-semibold text-white">{item.title}</h3>
              <p className="text-sm text-white/60">{item.detail}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* 4. Industry cards */}
      <Section className="border-t border-white/10" ariaLabel="Industries">
        <Eyebrow>Built for service businesses</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Who it&apos;s for</h2>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {INDUSTRY_CARDS.map((card) => (
            <Link key={card.href} href={card.href} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded-2xl">
              <Card className="h-full hover:bg-white/[0.07]">
                <h3 className="font-semibold text-white">{card.title}</h3>
                <p className="mt-2 text-sm text-white/60">{card.detail}</p>
              </Card>
            </Link>
          ))}
        </div>
      </Section>

      {/* 5. Product capabilities */}
      <Section className="border-t border-white/10" ariaLabel="Capabilities">
        <Eyebrow>Capabilities</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">What it actually does</h2>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map((cap) => (
            <div key={cap.title}>
              <h3 className="font-semibold text-white">{cap.title}</h3>
              <p className="mt-2 text-sm text-white/60">{cap.detail}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* 6. Dashboard showcase */}
      <Section className="border-t border-white/10" ariaLabel="Operations dashboard">
        <Eyebrow>Operations dashboard</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Everything your team needs, in one place</h2>
        <p className="mt-3 max-w-2xl text-white/60">
          Built from the same reusable dashboard components real tenants use — shown here with sample data.
        </p>
        <p className="mt-1 text-xs font-medium text-amber-300">Sample data — not a real customer.</p>
        <div className="mt-8 rounded-2xl border border-white/10 bg-mark-surface p-6 text-mark-ink">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Conversations" value="128" hint="Last 30 days" />
            <KpiCard label="Contact capture rate" value="74%" hint="Of qualifying conversations" />
            <KpiCard label="Pending appointments" value="9" hint="Awaiting confirmation" />
            <KpiCard label="Open handoffs" value="2" hint="Awaiting a team member" />
          </div>
          <div className="mt-6">
            <SimpleBarChart
              dates={["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
              series={[
                { label: "Widget conversations", color: "#7c3aed", values: [12, 18, 14, 22, 19, 9, 6] },
                { label: "Enquiries captured", color: "#22d3ee", values: [7, 10, 9, 15, 12, 5, 3] },
              ]}
            />
          </div>
        </div>
      </Section>

      {/* 7. Safety / security */}
      <Section className="border-t border-white/10" ariaLabel="Safety and security">
        <Eyebrow>Safety & security</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Deterministic safety, tenant isolation by design</h2>
        <p className="mt-4 max-w-2xl text-white/70">
          Emergency-language and professional-scope safety responses are fixed, non-model rules that run before any
          AI-generated reply — not a prompt instruction the model could ignore. Every tenant&apos;s conversations,
          contacts, and configuration are isolated from every other tenant.
        </p>
        <div className="mt-6">
          <SecondaryButton href="/security">Read the security overview</SecondaryButton>
        </div>
      </Section>

      {/* 8. Pricing preview */}
      <Section className="border-t border-white/10" ariaLabel="Pricing preview">
        <Eyebrow>Pricing</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Simple, transparent plans</h2>
        <p className="mt-2 text-sm text-amber-300">Placeholder pricing — final commercial pricing has not been approved.</p>
        <div className="mt-8 grid gap-6 sm:grid-cols-3">
          {pricingPlans.map((plan) => (
            <Card key={plan.id} className={plan.highlighted ? "border-mark-violet-500/50" : ""}>
              <h3 className="font-semibold text-white">{plan.name}</h3>
              <p className="mt-2 text-2xl font-semibold">
                {plan.monthlyPriceUsd === null ? "Contact us" : `$${plan.monthlyPriceUsd}/mo`}
              </p>
              <p className="mt-2 text-sm text-white/60">{plan.description}</p>
            </Card>
          ))}
        </div>
        <div className="mt-6">
          <SecondaryButton href="/pricing">See full plan comparison</SecondaryButton>
        </div>
      </Section>

      {/* 9. FAQ */}
      <Section className="border-t border-white/10" ariaLabel="Frequently asked questions">
        <Eyebrow>FAQ</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Common questions</h2>
        <div className="mt-8 flex flex-col divide-y divide-white/10">
          {FAQ_ITEMS.map((item) => (
            <details key={item.question} className="group py-4">
              <summary className="cursor-pointer list-none font-medium text-white marker:content-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded">
                {item.question}
              </summary>
              <p className="mt-2 text-sm text-white/60">{item.answer}</p>
            </details>
          ))}
        </div>
      </Section>

      {/* 10. Final CTA */}
      <Section className="border-t border-white/10 text-center" ariaLabel="Get started">
        <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">See it handle a real conversation.</h2>
        <p className="mx-auto mt-4 max-w-xl text-white/70">
          Try one of three interactive demos, or reach out and we&apos;ll walk you through it.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <PrimaryButton href="/demo">{brand.cta.primary}</PrimaryButton>
          <SecondaryButton href="/contact">{brand.cta.contact}</SecondaryButton>
        </div>
      </Section>
    </>
  );
}
