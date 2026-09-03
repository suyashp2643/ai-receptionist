import type { Metadata } from "next";
import { Card, Eyebrow, Section } from "@/components/marketing/ui";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Security",
  description: "Tenant isolation, deterministic safety rules, session security, and what's honestly not yet certified.",
  path: "/security",
});

const PRINCIPLES = [
  { title: "Tenant isolation", detail: "Every request resolves a tenant's role fresh from the database — never from a client-supplied value. A non-member gets a 404, not a 403, so tenant existence itself is never confirmed to an outsider." },
  { title: "Deterministic safety", detail: "Emergency-language and out-of-scope professional requests (medical, legal) are handled by fixed, non-model rules that run before any AI-generated response — not a prompt instruction the model could be talked around." },
  { title: "Scoped visitor sessions", detail: "The public widget uses a short-lived, revocable capability token scoped to one conversation — never a dashboard credential, and never transferable across tenants or installations." },
  { title: "Non-credentialed public API", detail: "The public widget API never accepts or sets cookies and never touches the dashboard's authentication state — a visitor's browser and a staff member's dashboard session are architecturally separate." },
  { title: "CSV export safety", detail: "Every export escapes formula-injection-prone values (leading =, +, -, @) with a protective character, verified against both malicious and ordinary values sharing the same prefix." },
  { title: "Zero-cost by default", detail: "Runs on a deterministic Mock AI with no external model calls by default — nothing is sent to a third-party AI provider unless one is explicitly configured." },
];

const NOT_CLAIMED = [
  "No compliance certification (SOC 2, ISO 27001, HIPAA, or similar) is claimed.",
  "No penetration test or third-party security audit has been performed.",
  "Data retention defaults are declared configuration only — no automated deletion job currently enforces them.",
  "The in-memory rate limiter is single-process; real capacity scales with worker count, not a hard global ceiling.",
];

export default function SecurityPage() {
  return (
    <>
      <Section className="pt-16 sm:pt-24">
        <Eyebrow>Security</Eyebrow>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Built with tenant isolation and deterministic safety in mind</h1>
        <p className="mt-5 max-w-2xl text-lg text-white/70">
          An honest account of what&apos;s actually implemented and verified — not a compliance claim.
        </p>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="Security principles">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {PRINCIPLES.map((p) => (
            <Card key={p.title}>
              <h2 className="font-semibold text-white">{p.title}</h2>
              <p className="mt-2 text-sm text-white/60">{p.detail}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section className="border-t border-white/10" ariaLabel="What is not claimed">
        <Eyebrow>What we don&apos;t claim</Eyebrow>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight">Honest limitations</h2>
        <ul className="mt-8 flex max-w-2xl flex-col gap-3">
          {NOT_CLAIMED.map((item) => (
            <li key={item} className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-100">
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-6 max-w-2xl text-sm text-white/50">
          Questions about a specific security requirement? Reach out via the contact page and we&apos;ll answer
          directly.
        </p>
      </Section>
    </>
  );
}
