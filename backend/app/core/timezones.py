import zoneinfo

# Single source of truth for "is this a valid timezone" across every schema
# that accepts one (auth, business profile, business location, tenant) and
# for the public /timezones listing endpoint the frontend populates its
# dropdowns from. Previously each schema computed its own
# `zoneinfo.available_timezones()` independently — harmless, but four copies
# of the same expensive call with no shared source of truth.
VALID_TIMEZONES: frozenset[str] = frozenset(zoneinfo.available_timezones())
SORTED_TIMEZONES: list[str] = sorted(VALID_TIMEZONES)

# Legacy IANA timezone names ("backward" links in the tzdata distribution)
# that some runtimes still report even though they're not present in every
# tzdata build's `available_timezones()`. Root-caused live: a browser's own
# `Intl.DateTimeFormat().resolvedOptions().timeZone` reported "Asia/Calcutta",
# which this backend's tzdata build has neither in `available_timezones()`
# nor constructible via `zoneinfo.ZoneInfo(...)` (raises "No time zone found
# with key Asia/Calcutta"). The dashboard's own timezone dropdown never hits
# this because it only ever submits a value sourced from this module's own
# SORTED_TIMEZONES (see docs/api.md's Timezones section) — but the public
# widget's appointment form falls back to the visitor's raw browser-reported
# timezone string when no location is selected, so it has no such guarantee.
# This is not an exhaustive list of every legacy alias in existence — just
# the ones plausible from a real browser — and is intentionally narrow: it
# normalizes a handful of well-known renames rather than attempting to
# reproduce the full tzdata "backward" file.
LEGACY_TIMEZONE_ALIASES: dict[str, str] = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Dacca": "Asia/Dhaka",
    "Asia/Macao": "Asia/Macau",
    "Asia/Thimbu": "Asia/Thimphu",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Europe/Kiev": "Europe/Kyiv",
    "Africa/Asmera": "Africa/Asmara",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Truk": "Pacific/Chuuk",
    "Pacific/Yap": "Pacific/Chuuk",
}


def normalize_timezone(name: str) -> str:
    """Maps a known legacy IANA alias to its canonical name, if applicable.

    Returns `name` unchanged when it isn't a known alias, or when the
    canonical target isn't itself in VALID_TIMEZONES (so this can never
    "normalize" into another invalid value) — callers should still validate
    the result against VALID_TIMEZONES before use.
    """
    canonical = LEGACY_TIMEZONE_ALIASES.get(name)
    if canonical is not None and canonical in VALID_TIMEZONES:
        return canonical
    return name
