import { describe, expect, it } from "vitest";
import { signInboundRequest } from "./hmac-sign";

describe("signInboundRequest", () => {
  it("matches the backend's HMAC-SHA256 scheme byte-for-byte (known test vector)", async () => {
    // Vector cross-checked against Python: hmac.new(b"test-secret",
    // b'1700000000.d1.e1.1.{"a":1}', hashlib.sha256).hexdigest() and against
    // Node's crypto.createHmac — both agree, matching
    // backend/app/integrations/signing.py::sign_payload's
    // "{timestamp}.{delivery_id}.{event_id}.{schema_version}.{body}" scheme.
    const { signature, timestamp } = await signInboundRequest("test-secret", {
      body: '{"a":1}',
      deliveryId: "d1",
      eventId: "e1",
      schemaVersion: "1",
      timestamp: "1700000000",
    });
    expect(timestamp).toBe("1700000000");
    expect(signature).toBe("adeef3283e45af8672a24118cd93889567c7852a5fd8f74a8fedd60acdbef90f");
  });

  it("produces a different signature when the body changes", async () => {
    const a = await signInboundRequest("secret", {
      body: '{"a":1}',
      deliveryId: "d1",
      eventId: "e1",
      schemaVersion: "1",
      timestamp: "100",
    });
    const b = await signInboundRequest("secret", {
      body: '{"a":2}',
      deliveryId: "d1",
      eventId: "e1",
      schemaVersion: "1",
      timestamp: "100",
    });
    expect(a.signature).not.toBe(b.signature);
  });

  it("produces a different signature for a retried delivery of the same event (delivery_id changes)", async () => {
    const first = await signInboundRequest("secret", {
      body: "{}",
      deliveryId: "delivery-1",
      eventId: "event-1",
      schemaVersion: "1",
      timestamp: "100",
    });
    const retry = await signInboundRequest("secret", {
      body: "{}",
      deliveryId: "delivery-2",
      eventId: "event-1",
      schemaVersion: "1",
      timestamp: "100",
    });
    expect(first.signature).not.toBe(retry.signature);
  });

  it("defaults the timestamp to the current time when none is supplied", async () => {
    const before = Math.floor(Date.now() / 1000);
    const { timestamp } = await signInboundRequest("secret", {
      body: "{}",
      deliveryId: "d1",
      eventId: "e1",
      schemaVersion: "1",
    });
    const after = Math.floor(Date.now() / 1000);
    const ts = Number(timestamp);
    expect(ts).toBeGreaterThanOrEqual(before);
    expect(ts).toBeLessThanOrEqual(after);
  });

  it("never returns the secret itself in the result", async () => {
    const secret = "super-secret-value-should-not-leak";
    const result = await signInboundRequest(secret, {
      body: "{}",
      deliveryId: "d1",
      eventId: "e1",
      schemaVersion: "1",
      timestamp: "100",
    });
    expect(JSON.stringify(result)).not.toContain(secret);
  });
});
