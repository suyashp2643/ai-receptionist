import type { Metadata } from "next";
import Link from "next/link";
import { Card, Eyebrow, MockAiBadge, Section } from "@/components/marketing/ui";
import { demos } from "@/lib/demos";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Interactive demos",
  description: "Try AI Receptionist live — clinic, hotel, and real estate demos, each an isolated, restartable conversation powered by deterministic Mock AI.",
  path: "/demo",
});

export default function DemoHubPage() {
  return (
    <Section className="pt-16 sm:pt-24">
      <Eyebrow>Interactive demos</Eyebrow>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">See it handle a real conversation</h1>
      <p className="mt-4 max-w-2xl text-white/70">
        Each demo is a real, fictional business running on the actual public widget and conversation engine —
        not a scripted animation. Every demo is isolated: restarting one never affects another.
      </p>
      <div className="mt-4">
        <MockAiBadge />
      </div>
      <div className="mt-10 grid gap-6 sm:grid-cols-3">
        {demos.map((demo) => (
          <Link
            key={demo.slug}
            href={`/demo/${demo.slug}`}
            className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded-2xl"
          >
            <Card className="h-full hover:bg-white/[0.07]">
              <p className="text-xs font-semibold uppercase tracking-wide text-mark-cyan-400">{demo.industryLabel}</p>
              <h2 className="mt-2 font-semibold text-white text-lg">{demo.businessName}</h2>
              <p className="mt-2 text-sm text-white/60">{demo.tagline}</p>
            </Card>
          </Link>
        ))}
      </div>
    </Section>
  );
}
