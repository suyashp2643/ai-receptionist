import { describe, expect, it } from "vitest";
import { absoluteUrl, breadcrumbJsonLd, buildMetadata, faqJsonLd, getSiteUrl, organizationJsonLd } from "./seo";

describe("getSiteUrl / absoluteUrl", () => {
  it("defaults safely to localhost for local development", () => {
    expect(getSiteUrl()).toBe("http://localhost:3000");
  });

  it("builds an absolute URL from a relative path", () => {
    expect(absoluteUrl("/pricing")).toBe("http://localhost:3000/pricing");
    expect(absoluteUrl("pricing")).toBe("http://localhost:3000/pricing");
  });
});

describe("buildMetadata", () => {
  it("sets title, description, canonical, and Open Graph fields", () => {
    const metadata = buildMetadata({ title: "Pricing", description: "Plans and pricing.", path: "/pricing" });
    expect(metadata.title).toBe("Pricing");
    expect(metadata.description).toBe("Plans and pricing.");
    expect(metadata.alternates?.canonical).toBe("http://localhost:3000/pricing");
    expect(metadata.openGraph?.url).toBe("http://localhost:3000/pricing");
  });

  it("indexes by default and can be opted out with noIndex", () => {
    const indexed = buildMetadata({ title: "A", description: "B", path: "/a" });
    expect(indexed.robots).toEqual({ index: true, follow: true });

    const noIndexed = buildMetadata({ title: "A", description: "B", path: "/a", noIndex: true });
    expect(noIndexed.robots).toEqual({ index: false, follow: false });
  });
});

describe("structured data helpers", () => {
  it("organizationJsonLd produces a valid Organization node", () => {
    const node = organizationJsonLd();
    expect(node["@type"]).toBe("Organization");
    expect(node.url).toBe("http://localhost:3000");
  });

  it("faqJsonLd maps question/answer pairs to FAQPage mainEntity", () => {
    const node = faqJsonLd([{ question: "Q1", answer: "A1" }]);
    expect(node["@type"]).toBe("FAQPage");
    expect(node.mainEntity).toHaveLength(1);
    expect(node.mainEntity[0].name).toBe("Q1");
    expect(node.mainEntity[0].acceptedAnswer.text).toBe("A1");
  });

  it("breadcrumbJsonLd produces positioned, absolute-URL list items", () => {
    const node = breadcrumbJsonLd([
      { name: "Industries", path: "/industries" },
      { name: "Clinics", path: "/industries/clinics" },
    ]);
    expect(node.itemListElement).toHaveLength(2);
    expect(node.itemListElement[0].position).toBe(1);
    expect(node.itemListElement[1].item).toBe("http://localhost:3000/industries/clinics");
  });
});
