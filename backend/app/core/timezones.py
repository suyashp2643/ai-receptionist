import zoneinfo

# Single source of truth for "is this a valid timezone" across every schema
# that accepts one (auth, business profile, business location, tenant) and
# for the public /timezones listing endpoint the frontend populates its
# dropdowns from. Previously each schema computed its own
# `zoneinfo.available_timezones()` independently — harmless, but four copies
# of the same expensive call with no shared source of truth.
VALID_TIMEZONES: frozenset[str] = frozenset(zoneinfo.available_timezones())
SORTED_TIMEZONES: list[str] = sorted(VALID_TIMEZONES)
