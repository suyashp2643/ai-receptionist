import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import {
  detectBrowserTimezone,
  normalizeTimezoneAlias,
  resolveDefaultTimezone,
  useTimezoneOptions,
} from "./timezones";

function mockDetectedTimezone(timeZone: string) {
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    timeZone,
  } as Intl.ResolvedDateTimeFormatOptions);
}

describe("normalizeTimezoneAlias", () => {
  it("maps the exact bug-report alias, Asia/Calcutta, to Asia/Kolkata", () => {
    expect(normalizeTimezoneAlias("Asia/Calcutta")).toBe("Asia/Kolkata");
  });

  it("maps other known legacy IANA links to their canonical form", () => {
    expect(normalizeTimezoneAlias("Europe/Kiev")).toBe("Europe/Kyiv");
    expect(normalizeTimezoneAlias("America/Buenos_Aires")).toBe("America/Argentina/Buenos_Aires");
    expect(normalizeTimezoneAlias("Asia/Saigon")).toBe("Asia/Ho_Chi_Minh");
  });

  it("passes an already-canonical timezone through unchanged", () => {
    expect(normalizeTimezoneAlias("Asia/Kolkata")).toBe("Asia/Kolkata");
    expect(normalizeTimezoneAlias("UTC")).toBe("UTC");
  });

  it("passes an unrecognized string through unchanged rather than inventing a mapping", () => {
    expect(normalizeTimezoneAlias("Not/ARealZone")).toBe("Not/ARealZone");
  });

  it("never maps an alias to another alias (no chained/double-hop entries)", () => {
    const aliasKeys = new Set(
      Object.keys({
        // Re-derived here rather than imported so this test still fails if
        // someone adds a chained alias without touching this file.
        "Africa/Asmera": 1,
        "America/Buenos_Aires": 1,
        "America/Catamarca": 1,
        "America/Cordoba": 1,
        "America/Godthab": 1,
        "America/Indianapolis": 1,
        "America/Jujuy": 1,
        "America/Louisville": 1,
        "America/Mendoza": 1,
        "Asia/Calcutta": 1,
        "Asia/Katmandu": 1,
        "Asia/Rangoon": 1,
        "Asia/Saigon": 1,
        "Atlantic/Faeroe": 1,
        "Europe/Kiev": 1,
        "Pacific/Enderbury": 1,
        "Pacific/Ponape": 1,
        "Pacific/Truk": 1,
      })
    );
    for (const key of aliasKeys) {
      const target = normalizeTimezoneAlias(key);
      expect(aliasKeys.has(target)).toBe(false);
    }
  });
});

describe("detectBrowserTimezone", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns UTC when Intl throws", () => {
    vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => {
      throw new Error("no Intl support");
    });
    expect(detectBrowserTimezone()).toBe("UTC");
  });
});

describe("resolveDefaultTimezone", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("normalizes a detected legacy alias to its canonical form when the canonical form is supported", () => {
    mockDetectedTimezone("Asia/Calcutta");
    expect(resolveDefaultTimezone(["UTC", "Asia/Kolkata"])).toBe("Asia/Kolkata");
  });

  it("uses the detected timezone as-is when it's already in the supported list", () => {
    mockDetectedTimezone("America/New_York");
    expect(resolveDefaultTimezone(["UTC", "America/New_York"])).toBe("America/New_York");
  });

  it("falls back to UTC when the detected (and normalized) timezone isn't supported", () => {
    mockDetectedTimezone("Not/ARealZone");
    expect(resolveDefaultTimezone(["UTC", "Asia/Kolkata"])).toBe("UTC");
  });

  it("falls back to UTC when the normalized alias's canonical form isn't in the supplied list", () => {
    // e.g. the supported list came from an older backend snapshot that
    // doesn't yet know about the canonical name — never crash, never
    // submit something unvalidated.
    mockDetectedTimezone("Asia/Calcutta");
    expect(resolveDefaultTimezone(["UTC"])).toBe("UTC");
  });

  it("falls back to UTC when detection itself throws", () => {
    vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => {
      throw new Error("boom");
    });
    expect(resolveDefaultTimezone(["UTC", "Asia/Kolkata"])).toBe("UTC");
  });
});

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}));

describe("useTimezoneOptions", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("populates the list from the backend once the fetch resolves", async () => {
    const { apiRequest } = await import("@/lib/api");
    vi.mocked(apiRequest).mockResolvedValue({ timezones: ["UTC", "Asia/Kolkata", "America/New_York"] });

    const { result } = renderHook(() => useTimezoneOptions());

    expect(result.current.timezones).toEqual(["UTC"]); // safe fallback before load
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.timezones).toEqual(["UTC", "Asia/Kolkata", "America/New_York"]);
  });

  it("keeps the UTC-only fallback if the backend request fails", async () => {
    const { apiRequest } = await import("@/lib/api");
    vi.mocked(apiRequest).mockRejectedValue(new Error("network error"));

    const { result } = renderHook(() => useTimezoneOptions());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.timezones).toEqual(["UTC"]);
  });
});
