import type { Metadata } from "next";
import { Card, Eyebrow, PrimaryButton, Section } from "@/components/marketing/ui";
import { pricingFaq, pricingPlans } from "@/lib/pricing";
import { buildMetadata, faqJsonLd } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Pricing",
  description: "Starter, Growth, and Scale plans — placeholder pricing pending final commercial approval. No checkout or payment processing.",
  path: "/pricing",
});

const COMPARISON_ROWS = [
  { label: "Receptionists", starter: "1", growth: "Multiple", scale: "Multiple" },
  { label: "Widget installations", starter: "1", growth: "Multiple", scale: "Multiple" },
  { label: "Team roles (owner/admin/member)", starter: "✓", growth: "✓", scale: "✓" },
  { label: "Analytics & operations dashboard", starter: "✓", growth: "✓", scale: "✓" },
  { label: "CSV export", starter: "—", growth: "✓", scale: "✓" },
  { label: "Priority support", starter: "—", growth: "✓", scale: "✓" },
  { label: "Custom usage volume", starter: "—", growth: "—", scale: "To be finalized" },
];

export default function PricingPage() {
  return (
    <>
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd(pricingFaq)) }}
      />

      <Section className="pt-16 sm:pt-24">
        <Eyebrow>Pricing</Eyebrow>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Simple, transparent plans</h1>
        <p className="mt-4 max-w-2xl text-white/70">
          Final commercial pricing has not been approved. Prices below are clearly marked, editable placeholders —
          not a finalized price list.
        </p>
        <p className="mt-2 text-sm font-medium text-amber-300">Placeholder pricing — subject to change.</p>

        <div className="mt-10 grid gap-6 sm:grid-cols-3">
          {pricingPlans.map((plan) => (
            <Card key={plan.id} className={plan.highlighted ? "border-mark-violet-500/50" : ""}>
              {plan.highlighted && (
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-mark-violet-300">
                  Most popular
                </p>
              )}
              <h2 className="font-semibold text-white text-lg">{plan.name}</h2>
              <p className="mt-2 text-3xl font-semibold">
                {plan.monthlyPriceUsd === null ? "Contact us" : `$${plan.monthlyPriceUsd}`}
                {plan.monthlyPriceUsd !== null && <span className="text-base font-normal text-white/50">/mo</span>}
              </p>
              {plan.annualPriceUsd !== null && (
                <p className="mt-1 text-xs text-white/50">${plan.annualPriceUsd}/mo billed annually (placeholder)</p>
              )}
              <p className="mt-3 text-sm text-white/60">{plan.description}</p>
              <ul className="mt-4 flex flex-col gap-2">
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2 text-sm text-white/75">
                    <span aria-hidden="true" className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-mark-cyan-400" />
                    {f}
                  </li>
                ))}
              </ul>
              <div className="mt-6">
                <PrimaryButton href="/contact" className="w-full">
                  Contact us
                </PrimaryButton>
              </div>
            </Card>
          ))}
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Plan comparison">
        <h2 className="text-2xl font-semibold tracking-tight">Feature comparison</h2>
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-white/50">
                <th scope="col" className="py-3 pr-4 font-medium">Feature</th>
                <th scope="col" className="py-3 px-4 font-medium">Starter</th>
                <th scope="col" className="py-3 px-4 font-medium">Growth</th>
                <th scope="col" className="py-3 px-4 font-medium">Scale</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON_ROWS.map((row) => (
                <tr key={row.label} className="border-b border-white/5">
                  <th scope="row" className="py-3 pr-4 text-left font-normal text-white/80">{row.label}</th>
                  <td className="py-3 px-4 text-white/70">{row.starter}</td>
                  <td className="py-3 px-4 text-white/70">{row.growth}</td>
                  <td className="py-3 px-4 text-white/70">{row.scale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-sm text-white/50">
          Usage and overage terms: to be finalized. Implementation and setup: details to be finalized and will
          depend on plan and configuration complexity.
        </p>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Pricing FAQ">
        <Eyebrow>FAQ</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Pricing questions</h2>
        <div className="mt-8 flex flex-col divide-y divide-white/10">
          {pricingFaq.map((item) => (
            <details key={item.question} className="group py-4">
              <summary className="cursor-pointer list-none font-medium text-white marker:content-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded">
                {item.question}
              </summary>
              <p className="mt-2 text-sm text-white/60">{item.answer}</p>
            </details>
          ))}
        </div>
      </Section>

      <Section className="border-t border-white/10 text-center" ariaLabel="Contact">
        <h2 className="text-3xl font-semibold tracking-tight">Questions about pricing?</h2>
        <div className="mt-6 flex justify-center">
          <PrimaryButton href="/contact">Contact us</PrimaryButton>
        </div>
      </Section>
    </>
  );
}
