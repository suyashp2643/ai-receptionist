import type { Metadata } from "next";
import { DemoDetailPage } from "@/components/marketing/DemoDetailPage";
import { getDemoBySlug } from "@/lib/demos";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Hotel demo",
  description: "Try the interactive hotel receptionist demo — amenities, policies, and a reservation request a staff member confirms.",
  path: "/demo/hotel",
});

export default function HotelDemoPage() {
  const demo = getDemoBySlug("hotel")!;
  return <DemoDetailPage demo={demo} industryHref="/industries/hotels" />;
}
