import { describe, expect, it } from "vitest";
import {
  CONNECTOR_TYPES,
  EVENT_TYPES,
  PII_EVENT_TYPES,
  SAFETY_EVENT_TYPES,
  SALES_EMPLOYEE_DISALLOWED_EVENT_TYPES,
  allowedEventTypesFor,
  connectorRequiresDestinationUrl,
  connectorRequiresSigningSecret,
} from "./integrations-api";

describe("connectorRequiresDestinationUrl", () => {
  it("is false only for the zero-network mock connector", () => {
    expect(connectorRequiresDestinationUrl("mock")).toBe(false);
    expect(connectorRequiresDestinationUrl("webhook")).toBe(true);
    expect(connectorRequiresDestinationUrl("revenue_brain")).toBe(true);
    expect(connectorRequiresDestinationUrl("sales_employee")).toBe(true);
  });
});

describe("connectorRequiresSigningSecret", () => {
  it("is false only for the zero-network mock connector", () => {
    expect(connectorRequiresSigningSecret("mock")).toBe(false);
    expect(connectorRequiresSigningSecret("webhook")).toBe(true);
    expect(connectorRequiresSigningSecret("revenue_brain")).toBe(true);
    expect(connectorRequiresSigningSecret("sales_employee")).toBe(true);
  });
});

describe("allowedEventTypesFor", () => {
  it("excludes safety.escalation_detected only for sales_employee", () => {
    for (const type of CONNECTOR_TYPES) {
      const allowed = allowedEventTypesFor(type);
      if (type === "sales_employee") {
        expect(allowed).not.toContain("safety.escalation_detected");
      } else {
        expect(allowed).toContain("safety.escalation_detected");
      }
    }
  });

  it("never allows a sales_employee-disallowed event type through", () => {
    const allowed = allowedEventTypesFor("sales_employee");
    for (const disallowed of SALES_EMPLOYEE_DISALLOWED_EVENT_TYPES) {
      expect(allowed).not.toContain(disallowed);
    }
  });

  it("returns every known event type for non-restricted connectors", () => {
    expect(new Set(allowedEventTypesFor("mock"))).toEqual(new Set(EVENT_TYPES));
    expect(new Set(allowedEventTypesFor("webhook"))).toEqual(new Set(EVENT_TYPES));
    expect(new Set(allowedEventTypesFor("revenue_brain"))).toEqual(new Set(EVENT_TYPES));
  });
});

describe("PII_EVENT_TYPES / SAFETY_EVENT_TYPES", () => {
  it("are disjoint — no event type is flagged as both a PII carrier and a safety classification", () => {
    for (const type of PII_EVENT_TYPES) {
      expect(SAFETY_EVENT_TYPES.has(type)).toBe(false);
    }
  });

  it("only contains known event types", () => {
    for (const type of PII_EVENT_TYPES) expect(EVENT_TYPES).toContain(type);
    for (const type of SAFETY_EVENT_TYPES) expect(EVENT_TYPES).toContain(type);
  });

  it("includes conversation.abandoned as a supported event with no PII or safety flag", () => {
    expect(EVENT_TYPES).toContain("conversation.abandoned");
    expect(PII_EVENT_TYPES.has("conversation.abandoned")).toBe(false);
    expect(SAFETY_EVENT_TYPES.has("conversation.abandoned")).toBe(false);
  });
});
