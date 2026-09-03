import type { Metadata } from "next";
import { ContactForm } from "@/components/marketing/ContactForm";
import { Eyebrow, Section } from "@/components/marketing/ui";
import { brand } from "@/lib/brand";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Contact",
  description: "Get in touch — ask a question, request a walkthrough, or tell us about your use case.",
  path: "/contact",
});

export default function ContactPage() {
  return (
    <Section className="pt-16 sm:pt-24 max-w-3xl">
      <Eyebrow>Contact</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Get in touch</h1>
      <p className="mt-4 text-white/70">
        Tell us about your business and we&apos;ll follow up — or reach us directly at{" "}
        <a href={`mailto:${brand.supportEmail}`} className="underline hover:text-white">
          {brand.supportEmail}
        </a>
        .
      </p>
      <div className="mt-10">
        <ContactForm />
      </div>
    </Section>
  );
}
