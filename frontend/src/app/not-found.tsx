import Link from "next/link";
import { BrandMark } from "@/components/marketing/BrandMark";
import { brand } from "@/lib/brand";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-mark-navy-950 px-6 text-center text-white">
      <BrandMark size={40} />
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Page not found</h1>
        <p className="mt-3 max-w-md text-white/60">
          The page you&apos;re looking for doesn&apos;t exist or may have moved. Here are a few places to go instead.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-4">
        <Link
          href="/"
          className="rounded-full bg-gradient-to-r from-mark-violet-500 to-mark-violet-600 px-6 py-3 text-sm font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
        >
          Go to homepage
        </Link>
        <Link
          href="/demo"
          className="rounded-full border border-mark-border px-6 py-3 text-sm font-semibold text-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
        >
          Try a live demo
        </Link>
        <Link
          href="/contact"
          className="rounded-full border border-mark-border px-6 py-3 text-sm font-semibold text-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
        >
          {brand.cta.contact}
        </Link>
      </div>
    </div>
  );
}
