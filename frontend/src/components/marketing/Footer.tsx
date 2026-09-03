import Link from "next/link";
import { BrandMark } from "@/components/marketing/BrandMark";
import { brand } from "@/lib/brand";

const COLUMNS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "Product",
    links: [
      { href: "/product", label: "Product" },
      { href: "/pricing", label: "Pricing" },
      { href: "/security", label: "Security" },
    ],
  },
  {
    title: "Industries",
    links: [
      { href: "/industries/clinics", label: "Clinics" },
      { href: "/industries/hotels", label: "Hotels" },
      { href: "/industries/real-estate", label: "Real estate" },
    ],
  },
  {
    title: "Demos",
    links: [
      { href: "/demo/clinic", label: "Clinic demo" },
      { href: "/demo/hotel", label: "Hotel demo" },
      { href: "/demo/real-estate", label: "Real estate demo" },
    ],
  },
  {
    title: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/contact", label: "Contact" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "/privacy", label: "Privacy" },
      { href: "/terms", label: "Terms" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-white/10 bg-mark-navy-950">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid grid-cols-2 gap-10 sm:grid-cols-3 lg:grid-cols-6">
          <div className="col-span-2 lg:col-span-1">
            <Link href="/" className="flex items-center gap-2 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded">
              <BrandMark size={24} />
              <span className="text-sm font-semibold">{brand.shortName}</span>
            </Link>
            <p className="mt-3 text-sm text-white/50">{brand.tagline}</p>
          </div>
          {COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-white/40">{col.title}</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-white/65 transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-6 text-xs text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <p>
            © {new Date().getFullYear()} {brand.legalName}. All demos on this site run on a deterministic,
            zero-cost Mock AI — not a live external model.
          </p>
          <p>
            Questions?{" "}
            <a href={`mailto:${brand.supportEmail}`} className="underline hover:text-white/70">
              {brand.supportEmail}
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
