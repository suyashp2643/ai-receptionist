import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContactForm } from "./ContactForm";

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Full name"), "Priya Sharma");
  await user.type(screen.getByLabelText("Work email"), "priya@example.com");
  await user.type(screen.getByLabelText("Company"), "Sunrise Clinics");
  await user.type(screen.getByLabelText("Country"), "United Arab Emirates");
  await user.type(screen.getByLabelText("Industry"), "Healthcare");
  await user.selectOptions(screen.getByLabelText("Team / company size"), "11-50");
  await user.selectOptions(screen.getByLabelText("Estimated monthly enquiries/conversations"), "201-500");
  await user.type(screen.getByLabelText("Primary use case"), "Qualify inbound clinic enquiries");
  await user.type(screen.getByLabelText("Message"), "We would like to see a live demo.");
}

describe("ContactForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("has a hidden honeypot field that is not part of the visible tab order", () => {
    render(<ContactForm />);
    const honeypot = screen.getByLabelText("Leave this field empty");
    expect(honeypot).toHaveAttribute("tabindex", "-1");
    expect(honeypot.closest("div")).toHaveAttribute("aria-hidden", "true");
  });

  it("separates contact consent (required) from marketing consent (optional)", () => {
    render(<ContactForm />);
    const contactConsent = screen.getByRole("checkbox", { name: /agree to be contacted/i });
    const marketingConsent = screen.getByRole("checkbox", { name: /occasional product updates/i });
    expect(contactConsent).toBeRequired();
    expect(marketingConsent).not.toBeRequired();
    expect(contactConsent).not.toBe(marketingConsent);
  });

  it("blocks submission and shows an error when contact consent is not given", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/contact/i);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("submits to the public leads endpoint and shows a generic success state", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ received: true }),
    });
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("checkbox", { name: /agree to be contacted/i }));
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/thanks/i);
    const [, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(options.body as string);
    expect(body.contact_consent).toBe(true);
    expect(body.marketing_consent).toBe(false);
    expect(body.hp_field).toBe("");
  });

  it("shows a specific message on a 429 rate-limit response", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: false, status: 429 });
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("checkbox", { name: /agree to be contacted/i }));
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many/i);
  });

  it("shows a generic error message when the network request fails", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("checkbox", { name: /agree to be contacted/i }));
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach/i);
  });
});
