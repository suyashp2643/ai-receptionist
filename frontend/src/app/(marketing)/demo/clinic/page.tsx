import type { Metadata } from "next";
import { DemoDetailPage } from "@/components/marketing/DemoDetailPage";
import { getDemoBySlug } from "@/lib/demos";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Clinic demo",
  description: "Try the interactive clinic receptionist demo — general information, appointment requests, and a real emergency-language safety response.",
  path: "/demo/clinic",
});

export default function ClinicDemoPage() {
  const demo = getDemoBySlug("clinic")!;
  return <DemoDetailPage demo={demo} industryHref="/industries/clinics" />;
}
