import type { Metadata } from "next";
import { DemoDetailPage } from "@/components/marketing/DemoDetailPage";
import { getDemoBySlug } from "@/lib/demos";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Real estate demo",
  description: "Try the interactive real estate receptionist demo — buyer qualification, property information, and site-visit requests.",
  path: "/demo/real-estate",
});

export default function RealEstateDemoPage() {
  const demo = getDemoBySlug("real-estate")!;
  return <DemoDetailPage demo={demo} industryHref="/industries/real-estate" />;
}
