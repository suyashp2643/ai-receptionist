import Link from "next/link";
import { DemoWidgetEmbed } from "@/components/marketing/DemoWidgetEmbed";
import { Eyebrow, MockAiBadge, Section } from "@/components/marketing/ui";
import type { DemoConfig } from "@/lib/demos";

export function DemoDetailPage({ demo, industryHref }: { demo: DemoConfig; industryHref: string }) {
  return (
    <Section className="pt-16 sm:pt-24">
      <Eyebrow>{demo.industryLabel} demo</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">{demo.businessName}</h1>
      <p className="mt-4 max-w-2xl text-white/70">{demo.tagline}</p>
      <div className="mt-4">
        <MockAiBadge />
      </div>

      <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_360px]">
        <DemoWidgetEmbed publicId={demo.publicId} title={`${demo.businessName} interactive demo`} height={620} />

        <aside className="flex flex-col gap-6">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-white/50">Try asking</h2>
            <ul className="mt-3 flex flex-col gap-2">
              {demo.suggestedQuestions.map((q) => (
                <li
                  key={q}
                  className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/80"
                >
                  {q}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-100">
            {demo.safetyNote}
          </div>
          <p className="text-sm text-white/60">
            Want to see how this looks configured for your business?{" "}
            <Link href={industryHref} className="underline hover:text-white">
              Read more about {demo.industryLabel.toLowerCase()}
            </Link>{" "}
            or <Link href="/contact" className="underline hover:text-white">get in touch</Link>.
          </p>
        </aside>
      </div>
    </Section>
  );
}
