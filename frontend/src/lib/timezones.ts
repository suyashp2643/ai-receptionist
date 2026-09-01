export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function getSupportedTimezones(): string[] {
  const intlWithSupportedValuesOf = Intl as unknown as {
    supportedValuesOf?: (key: string) => string[];
  };
  if (typeof intlWithSupportedValuesOf.supportedValuesOf === "function") {
    try {
      return intlWithSupportedValuesOf.supportedValuesOf("timeZone");
    } catch {
      return ["UTC"];
    }
  }
  return ["UTC"];
}
