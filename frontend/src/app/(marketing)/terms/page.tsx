import type { Metadata } from "next";
import { Eyebrow, Section } from "@/components/marketing/ui";
import { brand } from "@/lib/brand";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Terms",
  description: "Terms of use for this marketing site and its interactive demos.",
  path: "/terms",
});

export default function TermsPage() {
  return (
    <Section className="pt-16 sm:pt-24 max-w-3xl">
      <Eyebrow>Terms</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Terms of use</h1>
      <p className="mt-4 text-sm text-white/50">
        This is a plain-English description of how this site and its demos may be used, not a legally reviewed
        terms-of-service agreement, and does not constitute legal advice.
      </p>

      <div className="mt-10 flex flex-col gap-8 text-white/75">
        <section>
          <h2 className="text-xl font-semibold text-white">The interactive demos</h2>
          <p className="mt-2">
            The clinic, hotel, and real estate demos are fictional and run on a deterministic Mock AI — not a live
            external model. Nothing said in a demo is a real appointment, reservation, property transaction, or
            medical, legal, or financial advice. Demo data may be reset at any time.
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-white">No warranty</h2>
          <p className="mt-2">
            This site and its demos are provided as-is, for evaluation purposes, with no guarantee of availability,
            accuracy, or fitness for a particular purpose.
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-white">Acceptable use</h2>
          <p className="mt-2">
            Please don&apos;t submit real personal, medical, legal, or financial information into a demo, attempt to
            disrupt the site or its demos, or use automated tools to scrape or abuse the contact form.
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-white">Contact</h2>
          <p className="mt-2">
            Questions about these terms can be sent to{" "}
            <a href={`mailto:${brand.supportEmail}`} className="underline hover:text-white">
              {brand.supportEmail}
            </a>
            .
          </p>
        </section>
      </div>
    </Section>
  );
}
