import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DemoWidgetEmbed } from "./DemoWidgetEmbed";

describe("DemoWidgetEmbed", () => {
  it("mounts an iframe pointed at the sandboxed demo page for the given publicId", async () => {
    render(<DemoWidgetEmbed publicId="demo-clinic-sunrise" title="Clinic demo" />);
    const iframe = await screen.findByTitle("Clinic demo");
    expect(iframe).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
    const src = iframe.getAttribute("src") ?? "";
    expect(src.startsWith("/demo-widget.html?")).toBe(true);
    expect(src).toContain("publicId=demo-clinic-sunrise");
    expect(src).toContain("sessionNamespace=");
  });

  it("never includes an Authorization header, access token, or cookie value in the iframe src", async () => {
    render(<DemoWidgetEmbed publicId="demo-hotel-azurebay" title="Hotel demo" />);
    const iframe = await screen.findByTitle("Hotel demo");
    const src = iframe.getAttribute("src") ?? "";
    expect(src.toLowerCase()).not.toContain("authorization");
    expect(src.toLowerCase()).not.toContain("access_token");
    expect(src.toLowerCase()).not.toContain("refresh");
    expect(src.toLowerCase()).not.toContain("csrf");
  });

  it("restarting generates a new, different session namespace", async () => {
    const user = userEvent.setup();
    render(<DemoWidgetEmbed publicId="demo-realestate-falcon" title="Real estate demo" />);
    const before = await screen.findByTitle("Real estate demo");
    const beforeSrc = before.getAttribute("src") ?? "";
    const beforeNamespace = new URL(beforeSrc, "http://localhost").searchParams.get("sessionNamespace");

    await user.click(screen.getByRole("button", { name: "Restart demo" }));

    await waitFor(() => {
      const after = screen.getByTitle("Real estate demo");
      const afterSrc = after.getAttribute("src") ?? "";
      const afterNamespace = new URL(afterSrc, "http://localhost").searchParams.get("sessionNamespace");
      expect(afterNamespace).not.toBe(beforeNamespace);
    });
  });

  it("two demo instances (different publicId) never share a session namespace", async () => {
    render(
      <>
        <DemoWidgetEmbed publicId="demo-clinic-sunrise" title="Demo A" />
        <DemoWidgetEmbed publicId="demo-hotel-azurebay" title="Demo B" />
      </>
    );
    const a = await screen.findByTitle("Demo A");
    const b = await screen.findByTitle("Demo B");
    const nsA = new URL(a.getAttribute("src") ?? "", "http://localhost").searchParams.get("sessionNamespace");
    const nsB = new URL(b.getAttribute("src") ?? "", "http://localhost").searchParams.get("sessionNamespace");
    expect(nsA).toBeTruthy();
    expect(nsB).toBeTruthy();
    expect(nsA).not.toBe(nsB);
  });
});
