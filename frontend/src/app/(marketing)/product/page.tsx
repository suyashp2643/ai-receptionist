import type { Metadata } from "next";
import { ArchitectureDiagram } from "@/components/marketing/ArchitectureDiagram";
import { Card, Eyebrow, PrimaryButton, Section } from "@/components/marketing/ui";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Product",
  description: "How AI Receptionist works: visitor conversation, grounded retrieval, qualification, structured actions, staff dashboard, and security boundaries.",
  path: "/product",
});

const STAGES = [
  { title: "Visitor conversation", detail: "A visitor chats with the embedded widget — streaming responses, suggested questions, and optional browser voice." },
  { title: "Grounded retrieval", detail: "Answers are retrieved from your own FAQs and knowledge documents via full-text search — never invented, always with citations." },
  { title: "Qualification", detail: "Configurable fields capture what your team needs, validated as they're collected." },
  { title: "Structured actions", detail: "Contact capture, enquiry records, appointment requests, and human handoffs — each a typed record, not a buried transcript." },
  { title: "Staff dashboard", detail: "Your team manages conversations, contacts, enquiries, appointments, and handoffs, with analytics and CSV export." },
  { title: "Security boundaries", detail: "Every tenant's data is isolated; the public widget never shares a dashboard session or credentials." },
];

const LIMITATIONS = [
  "Uses a deterministic Mock AI by default — a real external model provider can be configured, but is not enabled by default.",
  "Multilingual widget support is planned, not yet available.",
  "No payment processing or calendar integration exists yet — appointment and reservation requests are collected for staff to confirm manually.",
  "Analytics are computed live from raw data on each request — no pre-aggregation or caching layer yet.",
];

export default function ProductPage() {
  return (
    <>
      <Section className="pt-16 sm:pt-24">
        <Eyebrow>Product</Eyebrow>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">How it works, end to end</h1>
        <p className="mt-5 max-w-2xl text-lg text-white/70">
          A grounded, tenant-safe AI front desk — from a visitor&apos;s first message to a structured record your team
          can act on.
        </p>
        <div className="mt-8">
          <PrimaryButton href="/demo">Try a live demo</PrimaryButton>
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Architecture">
        <Eyebrow>Architecture</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">The real request flow</h2>
        <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.02] p-6">
          <ArchitectureDiagram />
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="How it works in detail">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {STAGES.map((s) => (
            <Card key={s.title}>
              <h3 className="font-semibold text-white">{s.title}</h3>
              <p className="mt-2 text-sm text-white/60">{s.detail}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Current limitations">
        <Eyebrow>Current limitations & integration readiness</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">What it doesn&apos;t do yet</h2>
        <ul className="mt-8 flex max-w-2xl flex-col gap-3">
          {LIMITATIONS.map((item) => (
            <li key={item} className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white/70">
              {item}
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
