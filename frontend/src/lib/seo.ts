import type { Metadata } from "next";
import { brand } from "@/lib/brand";

/**
 * The canonical production domain — configurable via
 * NEXT_PUBLIC_SITE_URL, defaulting safely to localhost for local
 * development (never a guessed production domain). Used by every page's
 * canonical URL, Open Graph metadata, robots.ts, and sitemap.ts.
 */
export function getSiteUrl(): string {
  return process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
}

export function absoluteUrl(path: string): string {
  const base = getSiteUrl().replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export function buildMetadata(options: {
  title: string;
  description: string;
  path: string;
  noIndex?: boolean;
}): Metadata {
  const { title, description, path, noIndex } = options;
  const url = absoluteUrl(path);
  return {
    title,
    description,
    alternates: { canonical: url },
    robots: noIndex ? { index: false, follow: false } : { index: true, follow: true },
    openGraph: {
      title,
      description,
      url,
      siteName: brand.productName,
      type: "website",
      locale: "en_US",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export function organizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: brand.productName,
    url: getSiteUrl(),
    description: brand.metadata.defaultDescription,
  };
}

export function softwareApplicationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: brand.productName,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description: brand.metadata.defaultDescription,
    url: getSiteUrl(),
  };
}

export function faqJsonLd(items: { question: string; answer: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}

export function breadcrumbJsonLd(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}
