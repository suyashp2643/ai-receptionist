"""Controlled field mapping for an outbound event payload — rename,
include, omit, and default ONLY. No expression language, no templating,
no `eval`, nothing that reads as code: a mapping is a plain, closed JSON
object, safe to store as JSONB and safe to apply to a tenant-controlled
config against a payload that may itself contain nothing worse than
visitor-submitted plain text.

Applied to an event's `data` object only (never the envelope's own
`event_id`/`event_type`/`tenant_reference`/etc.) — see WebhookConnector's
own docstring and app/integrations/connectors/webhook.py for where this
plugs in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings


class FieldMappingError(ValueError):
    """Raised for a malformed or oversized mapping — safe to show to the
    authenticated owner/admin configuring the connection."""


@dataclass(frozen=True)
class FieldMapping:
    # old_key -> new_key. Applied before include/omit.
    rename: dict[str, str] = field(default_factory=dict)
    # If non-None, only these (post-rename) keys survive — an allow-list.
    include: tuple[str, ...] | None = None
    # Post-rename, post-include keys to drop.
    omit: tuple[str, ...] = ()
    # Keys to add if not already present after the above — never overwrites
    # a real value.
    defaults: dict[str, Any] = field(default_factory=dict)


_ALLOWED_KEYS = frozenset({"rename", "include", "omit", "defaults"})


def _check_depth(value: Any, *, max_depth: int, _current: int = 0) -> None:
    if _current > max_depth:
        raise FieldMappingError(f"Mapping default values may not nest deeper than {max_depth} levels.")
    if isinstance(value, dict):
        for v in value.values():
            _check_depth(v, max_depth=max_depth, _current=_current + 1)
    elif isinstance(value, list):
        for v in value:
            _check_depth(v, max_depth=max_depth, _current=_current + 1)


def validate_field_mapping(raw: dict | None, *, settings: Settings) -> FieldMapping:
    """Validates a connection's stored `config["field_mapping"]` (or
    returns the identity mapping if none is configured). Raises
    FieldMappingError for anything outside the closed rename/include/
    omit/defaults shape, oversized, or too deeply nested."""
    if not raw:
        return FieldMapping()

    if not isinstance(raw, dict):
        raise FieldMappingError("field_mapping must be an object.")
    unknown = set(raw.keys()) - _ALLOWED_KEYS
    if unknown:
        raise FieldMappingError(f"field_mapping has unrecognized keys: {sorted(unknown)}.")

    encoded_size = len(json.dumps(raw))
    if encoded_size > settings.integration_max_mapping_bytes:
        raise FieldMappingError(f"field_mapping may be at most {settings.integration_max_mapping_bytes} bytes.")

    rename = raw.get("rename", {})
    if not isinstance(rename, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in rename.items()):
        raise FieldMappingError("rename must be an object of string to string.")

    include_raw = raw.get("include")
    include: tuple[str, ...] | None = None
    if include_raw is not None:
        if not isinstance(include_raw, list) or not all(isinstance(x, str) for x in include_raw):
            raise FieldMappingError("include must be a list of strings.")
        include = tuple(include_raw)

    omit_raw = raw.get("omit", [])
    if not isinstance(omit_raw, list) or not all(isinstance(x, str) for x in omit_raw):
        raise FieldMappingError("omit must be a list of strings.")

    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise FieldMappingError("defaults must be an object.")
    _check_depth(defaults, max_depth=settings.integration_max_mapping_depth)

    return FieldMapping(rename=dict(rename), include=include, omit=tuple(omit_raw), defaults=dict(defaults))


def apply_field_mapping(data: dict, mapping: FieldMapping) -> dict:
    """Pure, side-effect-free transform: rename -> include -> omit ->
    defaults. Never mutates `data` itself."""
    result = dict(data)
    for old_key, new_key in mapping.rename.items():
        if old_key in result:
            result[new_key] = result.pop(old_key)

    if mapping.include is not None:
        result = {k: v for k, v in result.items() if k in mapping.include}

    for key in mapping.omit:
        result.pop(key, None)

    for key, value in mapping.defaults.items():
        result.setdefault(key, value)

    return result


def preview_field_mapping(sample_data: dict, raw_mapping: dict | None, *, settings: Settings) -> dict:
    """Used by the dashboard's mapping editor to show "here's what the
    receiver will get" against a small sample payload — never against a
    real event. Raises FieldMappingError for an invalid mapping, same as
    validate_field_mapping."""
    mapping = validate_field_mapping(raw_mapping, settings=settings)
    return apply_field_mapping(sample_data, mapping)
