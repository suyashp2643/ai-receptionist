/** Client-side HMAC-SHA256 signing, matching
 * backend/app/integrations/signing.py's scheme exactly — used only by the
 * integration lab (`/dashboard/integrations/lab`) to demonstrate a real,
 * correctly-signed call to this platform's OWN inbound API
 * (`/api/v1/integrations/inbound/events`), entirely over the same origin
 * this dashboard is served from. Never used to sign a request to any
 * third-party or external address. */

async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface SignedRequest {
  signature: string;
  timestamp: string;
}

/** Signing string: `{timestamp}.{deliveryId}.{eventId}.{schemaVersion}.{body}`
 * — must match app/integrations/signing.py::sign_payload byte-for-byte. */
export async function signInboundRequest(
  secret: string,
  {
    body,
    deliveryId,
    eventId,
    schemaVersion,
    timestamp,
  }: { body: string; deliveryId: string; eventId: string; schemaVersion: string; timestamp?: string }
): Promise<SignedRequest> {
  const ts = timestamp ?? String(Math.floor(Date.now() / 1000));
  const message = `${ts}.${deliveryId}.${eventId}.${schemaVersion}.${body}`;
  const signature = await hmacSha256Hex(secret, message);
  return { signature, timestamp: ts };
}
