import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Widget } from "./ui";
import type { WidgetConfig } from "./types";

const baseConfig: WidgetConfig = {
  status: "active",
  business_name: "Acme Real Estate",
  receptionist_name: "Ada",
  welcome_message: "Hi! How can I help?",
  suggested_questions: ["What are your hours?", "Do you have listings downtown?"],
  logo_url: null,
  accent_color: "#123456",
  supported_languages: ["en"],
  voice_enabled: true,
  theme: {},
  launcher_position: "bottom-right",
  ai_disclosure: "You are chatting with an automated assistant (mock demonstration mode).",
  privacy_notice: "We only use your info to respond to you.",
  mock_mode: true,
  business_public_email: "hello@acme.example",
  business_public_phone: null,
  services: [],
  locations: [],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function sseResponse(events: { event: string; data: unknown }[]): Response {
  const text = events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
  return new Response(stream);
}

function makeHost(): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  return host;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  window.sessionStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe("Widget mount", () => {
  it("renders a launcher inside a shadow root once config loads", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(baseConfig));
    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();

    const shadow = host.shadowRoot!;
    expect(shadow).not.toBeNull();
    expect(shadow.querySelector(".launcher")).not.toBeNull();
    expect(shadow.querySelector(".launcher")!.getAttribute("aria-label")).toContain("Ada");
  });

  it("renders nothing (does not throw) when the config fetch fails", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network down"));
    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await expect(widget.mount()).resolves.toBeUndefined();
    expect(host.shadowRoot?.querySelector(".launcher")).toBeNull();
  });

  it("shows the mock-mode badge when mock_mode is true", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(baseConfig));
    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();

    expect(host.shadowRoot!.querySelector(".badge")?.textContent).toBe("Demo AI");
  });

  it("does not leak its styles onto the host document", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(baseConfig));
    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();

    // The widget's <style> tag lives inside the shadow root, not in <head>.
    expect(document.head.querySelector("style")).toBeNull();
    expect(host.querySelector(".launcher")).toBeNull(); // only reachable via shadowRoot, not light DOM
  });

  it("omits the microphone button when speech recognition is unsupported", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(baseConfig));
    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();
    (host.shadowRoot!.querySelector(".launcher") as HTMLButtonElement).click();
    await Promise.resolve();

    expect(host.shadowRoot!.querySelector(".mic-button")).toBeNull();
  });
});

describe("Widget conversation flow", () => {
  it("starts a session and shows suggested questions on first open", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(baseConfig)) // config
      .mockResolvedValueOnce(
        jsonResponse({
          capability_token: "tok-1",
          expires_at: "2027-01-01T00:00:00Z",
          conversation: { id: "conv-1", status: "active", locale: "en", qualification_complete: false, started_at: "2026-01-01T00:00:00Z", last_message_at: null },
        })
      ); // sessions

    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();

    (host.shadowRoot!.querySelector(".launcher") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(host.shadowRoot!.querySelector(".bubble--assistant")).not.toBeNull());

    const suggested = host.shadowRoot!.querySelectorAll(".suggested button");
    expect(suggested.length).toBe(2);
    expect(fetchMock.mock.calls[1][0]).toBe("http://localhost:8000/api/v1/widget/pub-1/sessions");
  });

  it("sends a message and renders the streamed assistant response in the transcript", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(
        jsonResponse({
          capability_token: "tok-1",
          expires_at: "2027-01-01T00:00:00Z",
          conversation: { id: "conv-1", status: "active", locale: "en", qualification_complete: false, started_at: "2026-01-01T00:00:00Z", last_message_at: null },
        })
      )
      .mockResolvedValueOnce(
        sseResponse([
          { event: "message.started", data: { conversation_id: "conv-1", user_message_id: "u1", sequence_number: 0 } },
          { event: "response.delta", data: { delta: "We're open " } },
          { event: "response.delta", data: { delta: "9-5." } },
          {
            event: "response.completed",
            data: { message_id: "a1", sequence_number: 1, content: "We're open 9-5.", citations: [], safety_labels: [] },
          },
        ])
      );

    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();
    (host.shadowRoot!.querySelector(".launcher") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(host.shadowRoot!.querySelector(".bubble--assistant")).not.toBeNull());

    const textarea = host.shadowRoot!.querySelector("textarea")!;
    textarea.value = "What are your hours?";
    (host.shadowRoot!.querySelector(".send-button") as HTMLButtonElement).click();

    await vi.waitFor(() => {
      const bubbles = host.shadowRoot!.querySelectorAll(".bubble--assistant");
      expect(Array.from(bubbles).some((b) => b.textContent === "We're open 9-5.")).toBe(true);
    });

    const userBubbles = host.shadowRoot!.querySelectorAll(".bubble--user");
    expect(Array.from(userBubbles).some((b) => b.textContent === "What are your hours?")).toBe(true);
  });

  it("shows a friendly error and does not crash on a 429 response", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(jsonResponse({ error: { message: "Too many requests." } }, 429));

    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();
    (host.shadowRoot!.querySelector(".launcher") as HTMLButtonElement).click();

    await vi.waitFor(() => {
      const banner = host.shadowRoot!.querySelector(".error-banner") as HTMLElement;
      expect(banner.hidden).toBe(false);
      expect(banner.textContent).toContain("too quickly");
    });
  });
});

describe("Widget structured action forms", () => {
  async function mountAndOpen(host: HTMLElement): Promise<Widget> {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(baseConfig))
      .mockResolvedValueOnce(
        jsonResponse({
          capability_token: "tok-1",
          expires_at: "2027-01-01T00:00:00Z",
          conversation: { id: "conv-1", status: "active", locale: "en", qualification_complete: false, started_at: "2026-01-01T00:00:00Z", last_message_at: null },
        })
      );
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();
    (host.shadowRoot!.querySelector(".launcher") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(host.shadowRoot!.querySelector(".bubble--assistant")).not.toBeNull());
    return widget;
  }

  async function mountAndOpenWithConfig(host: HTMLElement, config: WidgetConfig): Promise<Widget> {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(config))
      .mockResolvedValueOnce(
        jsonResponse({
          capability_token: "tok-1",
          expires_at: "2027-01-01T00:00:00Z",
          conversation: { id: "conv-1", status: "active", locale: "en", qualification_complete: false, started_at: "2026-01-01T00:00:00Z", last_message_at: null },
        })
      );
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();
    (host.shadowRoot!.querySelector(".launcher") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(host.shadowRoot!.querySelector(".bubble--assistant")).not.toBeNull());
    return widget;
  }

  it("defaults marketing consent to unchecked in the contact form", async () => {
    const host = makeHost();
    await mountAndOpen(host);

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("contact")) as HTMLButtonElement).click();

    const consentCheckbox = host.shadowRoot!.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(consentCheckbox.checked).toBe(false);
  });

  it("shows pending-confirmation wording after an appointment request, never 'confirmed'", async () => {
    const host = makeHost();
    await mountAndOpen(host);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ reference: "abc-ref", status: "pending", message: "This is an appointment request, pending confirmation." })
    );

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();

    const dateInput = host.shadowRoot!.querySelector('input[type="date"]') as HTMLInputElement;
    dateInput.value = "2027-01-15";
    const submit = Array.from(host.shadowRoot!.querySelectorAll(".form-buttons button")).find((b) =>
      b.textContent?.includes("Submit request")
    ) as HTMLButtonElement;
    submit.click();

    await vi.waitFor(() => {
      const assistantBubbles = Array.from(host.shadowRoot!.querySelectorAll(".bubble--assistant"));
      const ackText = assistantBubbles.map((b) => b.textContent).join(" ");
      expect(ackText).toContain("pending confirmation");
      expect(ackText.toLowerCase()).not.toContain("confirmed.");
    });
  });

  it("omits service and location selectors when none are configured", async () => {
    const host = makeHost();
    await mountAndOpen(host); // baseConfig has empty services/locations

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();

    const selects = host.shadowRoot!.querySelectorAll(".form-overlay select");
    // Only the "preferred time of day" select should exist — no service/location pickers.
    expect(selects.length).toBe(1);
  });

  it("shows service and location selectors with a 'Not sure' option when configured", async () => {
    const host = makeHost();
    await mountAndOpenWithConfig(host, {
      ...baseConfig,
      services: [{ id: "svc-1", name: "Consultation", description: "A chat with an agent." }],
      locations: [{ id: "loc-1", name: "Downtown", timezone: "America/New_York" }],
    });

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();

    const labels = Array.from(host.shadowRoot!.querySelectorAll(".form-overlay label")).map((l) => l.textContent);
    expect(labels.some((t) => t?.includes("Service"))).toBe(true);
    expect(labels.some((t) => t?.includes("Location"))).toBe(true);

    const selects = Array.from(host.shadowRoot!.querySelectorAll(".form-overlay select")) as HTMLSelectElement[];
    // Exclude the unrelated "preferred time of day" select (Morning/Afternoon/Evening) —
    // only the service/location pickers should default to "Not sure".
    const pickerSelects = selects.filter((s) => s.options[0].text !== "Morning");
    expect(pickerSelects.length).toBe(2);
    for (const select of pickerSelects) {
      expect(select.options[0].text).toBe("Not sure");
      expect(select.options[0].value).toBe("");
    }
  });

  it("submits the selected service/location ids and uses the location's own timezone", async () => {
    const host = makeHost();
    await mountAndOpenWithConfig(host, {
      ...baseConfig,
      services: [{ id: "svc-1", name: "Consultation", description: null }],
      locations: [{ id: "loc-1", name: "Auckland Office", timezone: "Pacific/Auckland" }],
    });
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ reference: "abc-ref", status: "pending", message: "pending confirmation" })
    );

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();

    const dateInput = host.shadowRoot!.querySelector('input[type="date"]') as HTMLInputElement;
    dateInput.value = "2027-01-15";
    const selects = Array.from(host.shadowRoot!.querySelectorAll(".form-overlay select")) as HTMLSelectElement[];
    const serviceSelect = selects.find((s) => Array.from(s.options).some((o) => o.text === "Consultation"))!;
    const locationSelect = selects.find((s) => Array.from(s.options).some((o) => o.text === "Auckland Office"))!;
    serviceSelect.value = "svc-1";
    locationSelect.value = "loc-1";

    const submit = Array.from(host.shadowRoot!.querySelectorAll(".form-buttons button")).find((b) =>
      b.textContent?.includes("Submit request")
    ) as HTMLButtonElement;
    submit.click();

    await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3));
    const [, options] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    const body = JSON.parse(options.body as string);
    expect(body.service_id).toBe("svc-1");
    expect(body.location_id).toBe("loc-1");
    expect(body.timezone).toBe("Pacific/Auckland");
  });

  it("acknowledges a handoff request without promising an immediate response", async () => {
    const host = makeHost();
    await mountAndOpen(host);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ reference: "handoff-ref", status: "open", message: "A team member will follow up with you." })
    );

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("human")) as HTMLButtonElement).click();

    const textarea = host.shadowRoot!.querySelector(".form-overlay textarea") as HTMLTextAreaElement;
    textarea.value = "I have a billing question.";
    const submit = Array.from(host.shadowRoot!.querySelectorAll(".form-buttons button")).find((b) =>
      b.textContent?.includes("Request callback")
    ) as HTMLButtonElement;
    submit.click();

    await vi.waitFor(() => {
      const assistantBubbles = Array.from(host.shadowRoot!.querySelectorAll(".bubble--assistant"));
      expect(assistantBubbles.some((b) => b.textContent?.includes("follow up"))).toBe(true);
    });
  });

  it("shows a validation error inside the form overlay, not the hidden main banner", async () => {
    const host = makeHost();
    await mountAndOpen(host);

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();
    const submit = Array.from(host.shadowRoot!.querySelectorAll(".form-buttons button")).find((b) =>
      b.textContent?.includes("Submit request")
    ) as HTMLButtonElement;
    submit.click(); // no date chosen

    const formError = host.shadowRoot!.querySelector(".form-overlay .form-error") as HTMLElement;
    expect(formError.hidden).toBe(false);
    expect(formError.textContent).toContain("preferred date");
    // The main conversation error banner (hidden behind the full-panel
    // overlay) must not be the one used for a form's own validation errors.
    expect((host.shadowRoot!.querySelector(".error-banner") as HTMLElement).hidden).toBe(true);
  });

  it("shows the server's own safe validation message for a 422, not a generic fallback", async () => {
    const host = makeHost();
    await mountAndOpen(host);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { message: "Requested date cannot be in the past." } }, 422)
    );

    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();
    const dateInput = host.shadowRoot!.querySelector('input[type="date"]') as HTMLInputElement;
    dateInput.value = "2020-01-01";
    const submit = Array.from(host.shadowRoot!.querySelectorAll(".form-buttons button")).find((b) =>
      b.textContent?.includes("Submit request")
    ) as HTMLButtonElement;
    submit.click();

    await vi.waitFor(() => {
      const formError = host.shadowRoot!.querySelector(".form-overlay .form-error") as HTMLElement;
      expect(formError.hidden).toBe(false);
      expect(formError.textContent).toBe("Requested date cannot be in the past.");
    });
  });

  it("only allows one structured action form open at a time", async () => {
    const host = makeHost();
    await mountAndOpen(host);
    const buttons = Array.from(host.shadowRoot!.querySelectorAll(".actions-row button"));
    (buttons.find((b) => b.textContent?.includes("contact")) as HTMLButtonElement).click();
    (buttons.find((b) => b.textContent?.includes("appointment")) as HTMLButtonElement).click();

    expect(host.shadowRoot!.querySelectorAll(".form-overlay").length).toBe(1);
  });
});

describe("Widget cleanup", () => {
  it("removes its host element and shadow content on destroy", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(baseConfig));
    const host = makeHost();
    const widget = new Widget({ publicId: "pub-1", apiBaseUrl: "http://localhost:8000" }, host);
    await widget.mount();

    widget.destroy();

    expect(document.body.contains(host)).toBe(false);
  });
});
