import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";

// A handful of well-known IANA "backward" compatibility links that some
// browsers' ICU builds still report from Intl.supportedValuesOf('timeZone')
// / Intl.DateTimeFormat().resolvedOptions().timeZone, but that this
// project's backend (Python's `zoneinfo.available_timezones()`) does not
// include as canonical names — e.g. a browser in India reporting
// "Asia/Calcutta" instead of "Asia/Kolkata". This map is NOT the source of
// truth for which timezones are valid — fetchSupportedTimezones() (backed
// by the backend's own zoneinfo database) is — it only exists to pick a
// nicer default when the browser's own detection lands on a legacy alias.
// If a name is missing here, resolveDefaultTimezone() below simply falls
// back to "UTC" rather than guessing wrong, so an incomplete list can never
// cause an invalid submission — only a less specific default in a rare
// edge case.
const KNOWN_BROWSER_TIMEZONE_ALIASES: Record<string, string> = {
  "Africa/Asmera": "Africa/Asmara",
  "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
  "America/Catamarca": "America/Argentina/Catamarca",
  "America/Cordoba": "America/Argentina/Cordoba",
  "America/Godthab": "America/Nuuk",
  "America/Indianapolis": "America/Indiana/Indianapolis",
  "America/Jujuy": "America/Argentina/Jujuy",
  "America/Louisville": "America/Kentucky/Louisville",
  "America/Mendoza": "America/Argentina/Mendoza",
  "Asia/Calcutta": "Asia/Kolkata",
  "Asia/Katmandu": "Asia/Kathmandu",
  "Asia/Rangoon": "Asia/Yangon",
  "Asia/Saigon": "Asia/Ho_Chi_Minh",
  "Atlantic/Faeroe": "Atlantic/Faroe",
  "Europe/Kiev": "Europe/Kyiv",
  "Pacific/Enderbury": "Pacific/Kanton",
  "Pacific/Ponape": "Pacific/Pohnpei",
  "Pacific/Truk": "Pacific/Chuuk",
};

export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** Best-effort normalization of a known legacy IANA link name to its
 * modern canonical form. Returns the input unchanged if it isn't a
 * recognized alias — never the sole safety net, since the caller still
 * checks the result against the backend-supplied valid list. */
export function normalizeTimezoneAlias(timezone: string): string {
  return KNOWN_BROWSER_TIMEZONE_ALIASES[timezone] ?? timezone;
}

/** Picks a safe default for a fresh registration: the browser's detected
 * zone, normalized if it's a known alias, falling back to "UTC" if it
 * still isn't in the backend's supported set. `supported` should come from
 * fetchSupportedTimezones() — never an empty/unfetched list, or every
 * detected zone will fall back to UTC. */
export function resolveDefaultTimezone(supported: string[]): string {
  const normalized = normalizeTimezoneAlias(detectBrowserTimezone());
  return supported.includes(normalized) ? normalized : "UTC";
}

interface TimezoneListResponse {
  timezones: string[];
}

/** The backend's own `zoneinfo.available_timezones()` set, sorted —
 * anything rendered from this list is guaranteed to pass the backend's
 * timezone validators, unlike the browser's Intl-supplied list (which
 * includes legacy aliases the backend's tzdata build doesn't recognize). */
export function fetchSupportedTimezones(): Promise<string[]> {
  return apiRequest<TimezoneListResponse>("/api/v1/timezones").then((data) => data.timezones);
}

/** Shared client hook: fetches the backend's canonical timezone list once
 * per mount. Falls back to `["UTC"]` if the request fails, so a form never
 * renders with an empty or broken picker. */
export function useTimezoneOptions(): { timezones: string[]; isLoading: boolean } {
  const [timezones, setTimezones] = useState<string[]>(["UTC"]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchSupportedTimezones()
      .then((list) => {
        if (!cancelled) setTimezones(list);
      })
      .catch(() => {
        // Keep the UTC-only fallback — never leave the picker empty.
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { timezones, isLoading };
}
