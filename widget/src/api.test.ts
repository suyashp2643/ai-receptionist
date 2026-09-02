import { afterEach, describe, expect, it, vi } from "vitest";
import { readSSE, WidgetApiClient } from "./api";
import { WidgetApiError } from "./types";

function sseResponse(text: string): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
  return new Response(stream);
}

describe("readSSE", () => {
  it("parses multiple events out of one chunk", async () => {
    const response = sseResponse(
      'event: response.delta\ndata: {"delta":"Hi"}\n\n' + 'event: response.completed\ndata: {"message_id":"m1"}\n\n'
    );
    const events = [];
    for await (const event of readSSE(response)) events.push(event);
    expect(events).toEqual([
      { event: "response.delta", data: { delta: "Hi" } },
      { event: "response.completed", data: { message_id: "m1" } },
    ]);
  });

  it("ignores a trailing incomplete event with no terminating blank line", async () => {
    const response = sseResponse('event: response.delta\ndata: {"delta":"Hi"}\n\nevent: incomplete\ndata: {"a":1}');
    const events = [];
    for await (const event of readSSE(response)) events.push(event);
    expect(events).toEqual([{ event: "response.delta", data: { delta: "Hi" } }]);
  });

  it("yields nothing for a response with no body", async () => {
    const response = new Response(null);
    const events = [];
    for await (const event of readSSE(response)) events.push(event);
    expect(events).toEqual([]);
  });
});

describe("WidgetApiClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds the config URL from apiBaseUrl and publicId", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ mock_mode: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new WidgetApiClient({ apiBaseUrl: "http://localhost:8000/", publicId: "abc123" });
    await client.getConfig();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/v1/widget/abc123/config");
  });

  it("sends the capability token header on token-scoped calls", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ conversation: {}, messages: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new WidgetApiClient({ apiBaseUrl: "http://localhost:8000", publicId: "abc123" });
    await client.getConversation("secret-token", "conv-1");

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers["X-Widget-Session-Token"]).toBe("secret-token");
  });

  it("throws WidgetApiError with the server's error message on a non-2xx response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { message: "Too many requests." } }), { status: 429 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new WidgetApiClient({ apiBaseUrl: "http://localhost:8000", publicId: "abc123" });
    await expect(client.startSession()).rejects.toMatchObject(
      new WidgetApiError(429, "Too many requests.")
    );
  });
});
