import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/seo";

const PUBLIC_PATHS = [
  "/",
  "/product",
  "/industries",
  "/industries/clinics",
  "/industries/hotels",
  "/industries/real-estate",
  "/demo",
  "/demo/clinic",
  "/demo/hotel",
  "/demo/real-estate",
  "/pricing",
  "/security",
  "/about",
  "/contact",
  "/privacy",
  "/terms",
];

export default function sitemap(): MetadataRoute.Sitemap {
  return PUBLIC_PATHS.map((path) => ({
    url: absoluteUrl(path),
    changeFrequency: "weekly" as const,
    priority: path === "/" ? 1 : 0.7,
  }));
}
