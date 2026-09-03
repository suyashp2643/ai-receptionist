import type { ReactNode } from "react";
import { Footer } from "@/components/marketing/Footer";
import { Header } from "@/components/marketing/Header";

/** Wraps every public marketing route (/, /product, /industries/*, /demo/*,
 * /pricing, /security, /about, /contact, /privacy, /terms) in the shared
 * public layout — sticky nav + footer. Deliberately a separate route group
 * from dashboard/login/onboarding, which keep their own layouts
 * untouched. */
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-mark-navy-950 text-white">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <Header />
      <main id="main-content">{children}</main>
      <Footer />
    </div>
  );
}
