import type { Metadata } from "next";
import { Eyebrow, PrimaryButton, Section } from "@/components/marketing/ui";
import { brand } from "@/lib/brand";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "About",
  description: `About ${brand.productName} — a grounded, tenant-safe AI front desk for service businesses.`,
  path: "/about",
});

export default function AboutPage() {
  return (
    <Section className="pt-16 sm:pt-24">
      <Eyebrow>About</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">{brand.productName}</h1>
      <p className="mt-5 max-w-2xl text-lg text-white/70">{brand.description}</p>
      <div className="mt-8 flex max-w-2xl flex-col gap-4 text-white/70">
        <p>
          We built {brand.productName} around a simple idea: a visitor&apos;s question deserves a grounded answer,
          and a business&apos;s staff deserve a structured record of what happened — not a chat transcript to dig
          through.
        </p>
        <p>
          Every demo on this site runs on the same conversation engine, safety rules, and tenant-isolation model a
          real deployment uses — including the deterministic Mock AI powering the public demos, so behavior stays
          honest and reproducible.
        </p>
      </div>
      <div className="mt-8 flex gap-4">
        <PrimaryButton href="/demo">Try a live demo</PrimaryButton>
      </div>
    </Section>
  );
}
