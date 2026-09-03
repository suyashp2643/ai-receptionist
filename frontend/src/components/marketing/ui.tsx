import Link from "next/link";
import type { ReactNode } from "react";

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mark-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-mark-navy-950";

export function PrimaryButton({
  href,
  children,
  className = "",
  ...rest
}: {
  href: string;
  children: ReactNode;
  className?: string;
} & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center rounded-full bg-gradient-to-r from-mark-violet-500 to-mark-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-mark-violet-600/20 transition hover:from-mark-violet-400 hover:to-mark-violet-500 ${focusRing} ${className}`}
      {...rest}
    >
      {children}
    </Link>
  );
}

export function SecondaryButton({
  href,
  children,
  className = "",
  ...rest
}: {
  href: string;
  children: ReactNode;
  className?: string;
} & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center rounded-full border border-mark-border px-6 py-3 text-sm font-semibold text-white/90 transition hover:border-mark-violet-400 hover:text-white ${focusRing} ${className}`}
      {...rest}
    >
      {children}
    </Link>
  );
}

export function Section({
  children,
  className = "",
  id,
  ariaLabel,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
  ariaLabel?: string;
}) {
  return (
    <section id={id} aria-label={ariaLabel} className={`mx-auto w-full max-w-6xl px-6 py-16 sm:py-20 ${className}`}>
      {children}
    </section>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-mark-cyan-400">{children}</p>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-white/[0.04] p-6 backdrop-blur-sm transition hover:border-mark-violet-500/40 ${className}`}
    >
      {children}
    </div>
  );
}

export function MockAiBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-mark-cyan-500/40 bg-mark-cyan-500/10 px-3 py-1 text-xs font-medium text-mark-cyan-400 ${className}`}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-mark-cyan-400" />
      Mock AI demo — not a live external model
    </span>
  );
}
