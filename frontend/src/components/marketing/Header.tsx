"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { BrandMark } from "@/components/marketing/BrandMark";
import { brand } from "@/lib/brand";

const NAV_LINKS = [
  { href: "/product", label: "Product" },
  { href: "/industries", label: "Industries" },
  { href: "/demo", label: "Demos" },
  { href: "/pricing", label: "Pricing" },
  { href: "/security", label: "Security" },
];

export function Header() {
  const [open, setOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-mark-navy-950/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded">
          <BrandMark size={26} />
          <span className="text-base font-semibold">{brand.shortName}</span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-8 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-white/75 transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-4 lg:flex">
          <Link
            href="/login"
            className="text-sm font-medium text-white/75 transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 rounded"
          >
            Login
          </Link>
          <Link
            href="/demo"
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-mark-violet-500 to-mark-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-mark-violet-600/20 transition hover:from-mark-violet-400 hover:to-mark-violet-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-mark-navy-950"
          >
            {brand.cta.primary}
          </Link>
        </div>

        <button
          ref={menuButtonRef}
          type="button"
          className="inline-flex items-center justify-center rounded-md p-2 text-white/90 lg:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          ) : (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          )}
        </button>
      </div>

      {open && (
        <nav
          id="mobile-nav"
          aria-label="Mobile"
          className="border-t border-white/10 bg-mark-navy-950 px-6 pb-6 pt-2 lg:hidden"
        >
          <ul className="flex flex-col gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-lg px-3 py-3 text-sm font-medium text-white/85 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <Link
                href="/login"
                onClick={() => setOpen(false)}
                className="block rounded-lg px-3 py-3 text-sm font-medium text-white/85 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
              >
                Login
              </Link>
            </li>
            <li className="pt-2">
              <Link
                href="/demo"
                onClick={() => setOpen(false)}
                className="block rounded-full bg-gradient-to-r from-mark-violet-500 to-mark-violet-600 px-4 py-3 text-center text-sm font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400"
              >
                {brand.cta.primary}
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </header>
  );
}
