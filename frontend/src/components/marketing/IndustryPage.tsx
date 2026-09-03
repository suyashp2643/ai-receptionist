import { Card, Eyebrow, PrimaryButton, Section } from "@/components/marketing/ui";
import { breadcrumbJsonLd, faqJsonLd } from "@/lib/seo";

export type IndustryPageContent = {
  slug: string;
  name: string;
  headline: string;
  subhead: string;
  painPoints: string[];
  workflow: { title: string; detail: string }[];
  capabilities: string[];
  safety: string[];
  demoHref: string;
  demoLabel: string;
  faq: { question: string; answer: string }[];
};

export function IndustryPage({ content }: { content: IndustryPageContent }) {
  return (
    <>
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(
            breadcrumbJsonLd([
              { name: "Industries", path: "/industries" },
              { name: content.name, path: `/industries/${content.slug}` },
            ])
          ),
        }}
      />
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd(content.faq)) }}
      />

      <Section className="pt-16 sm:pt-24">
        <Eyebrow>{content.name}</Eyebrow>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">{content.headline}</h1>
        <p className="mt-5 max-w-2xl text-lg text-white/70">{content.subhead}</p>
        <div className="mt-8">
          <PrimaryButton href={content.demoHref}>{content.demoLabel}</PrimaryButton>
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Common challenges">
        <Eyebrow>Common challenges</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">What it solves</h2>
        <ul className="mt-8 grid gap-4 sm:grid-cols-2">
          {content.painPoints.map((point) => (
            <li key={point} className="flex gap-3 text-white/75">
              <span aria-hidden="true" className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-mark-cyan-400" />
              {point}
            </li>
          ))}
        </ul>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Workflow">
        <Eyebrow>Workflow</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">How a conversation flows</h2>
        <ol className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {content.workflow.map((step, i) => (
            <li key={step.title} className="flex flex-col gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-mark-violet-500/20 text-sm font-semibold text-mark-violet-300">
                {i + 1}
              </span>
              <h3 className="font-semibold text-white">{step.title}</h3>
              <p className="text-sm text-white/60">{step.detail}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Capabilities">
        <Eyebrow>Capabilities</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">What it does for {content.name.toLowerCase()}</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {content.capabilities.map((cap) => (
            <Card key={cap}>
              <p className="text-sm text-white/80">{cap}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Safety and limitations">
        <Eyebrow>Safety & limitations</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">What it doesn&apos;t do</h2>
        <ul className="mt-8 flex max-w-2xl flex-col gap-3">
          {content.safety.map((item) => (
            <li key={item} className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-100">
              {item}
            </li>
          ))}
        </ul>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Frequently asked questions">
        <Eyebrow>FAQ</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Common questions</h2>
        <div className="mt-8 flex flex-col divide-y divide-white/10">
          {content.faq.map((item) => (
            <details key={item.question} className="group py-4">
              <summary className="cursor-pointer list-none font-medium text-white marker:content-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded">
                {item.question}
              </summary>
              <p className="mt-2 text-sm text-white/60">{item.answer}</p>
            </details>
          ))}
        </div>
      </Section>

      <Section className="border-t border-white/10 text-center" ariaLabel="Get started">
        <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">See it handle a real {content.name.toLowerCase()} conversation.</h2>
        <div className="mt-8 flex justify-center">
          <PrimaryButton href={content.demoHref}>{content.demoLabel}</PrimaryButton>
        </div>
      </Section>
    </>
  );
}
