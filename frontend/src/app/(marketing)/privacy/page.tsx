import type { Metadata } from "next";
import { Eyebrow, Section } from "@/components/marketing/ui";
import { brand } from "@/lib/brand";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Privacy",
  description: "What information this site and its demos collect, and how it's used.",
  path: "/privacy",
});

export default function PrivacyPage() {
  return (
    <Section className="pt-16 sm:pt-24 max-w-3xl">
      <Eyebrow>Privacy</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Privacy notice</h1>
      <p className="mt-4 text-sm text-white/50">
        This is a plain-English notice, not a legally reviewed privacy policy, and does not constitute legal advice.
        It describes what this marketing site and its demos actually do — no compliance certification or legal
        conclusion is claimed.
      </p>

      <div className="mt-10 flex flex-col gap-8 text-white/75">
        <section>
          <h2 className="text-xl font-semibold text-white">What this site collects</h2>
          <p className="mt-2">
            This marketing site does not use third-party analytics or advertising trackers. If you submit the
            contact form, we collect the fields you enter (name, work email, company, and the other fields shown on
            that form) to respond to your enquiry — see the contact page for the exact fields and consent language.
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-white">The interactive demos</h2>
          <p className="mt-2">
            The clinic, hotel, and real estate demos run on fictional demonstration businesses using a deterministic
            Mock AI. Messages you send in a demo may be stored the same way a real visitor conversation would be
            stored, scoped to that fictional demo business — never linked to your identity, and never mixed with
            any other tenant&apos;s data. Demo conversations are periodically reset by the operator; do not enter
            real
            personal or sensitive information into a demo.
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-white">Consent</h2>
          <p className="mt-2">
            The contact form separates consent to be contacted about your enquiry from optional marketing consent —
            the two are never combined into a single checkbox, and marketing consent is never required to submit
            the form.
          </p>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-white">Contact</h2>
          <p className="mt-2">
            Questions about this notice can be sent to{" "}
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
