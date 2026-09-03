"""Reusable, secure CSV generation for Phase 6's owner/admin-only exports.
Every export route must build its rows through `build_csv`, never hand-roll
its own `csv.writer` — the injection guard and size cap live here exactly
once.

CSV injection: a cell whose value starts with `=`, `+`, `-`, or `@` is
interpreted as a formula by Excel/Sheets/LibreOffice when the file is
opened, which can execute arbitrary lookups (or worse, with legacy DDE)
against the opening user's machine. Prefixing such a value with a single
quote (`'`) is the standard mitigation — spreadsheet applications treat a
leading `'` as "force text" and strip it from the *displayed* value, so the
export stays readable while never being interpreted as a formula."""

import csv
import io
from collections.abc import Iterable, Sequence

_FORMULA_PREFIXES = ("=", "+", "-", "@")

MAX_EXPORT_ROWS = 10_000


class ExportTooLargeError(Exception):
    pass


def _escape_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def build_csv(*, header: Sequence[str], rows: Iterable[Sequence[object]], max_rows: int = MAX_EXPORT_ROWS) -> str:
    """Returns a complete CSV document as a single in-memory string — never
    written to disk (see every export route's docstring). Raises
    ExportTooLargeError if `rows` would exceed `max_rows`; callers should
    bound their own query with `LIMIT max_rows + 1` so this is detected
    without materializing an unbounded result set."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    count = 0
    for row in rows:
        count += 1
        if count > max_rows:
            raise ExportTooLargeError(f"Export exceeds the maximum of {max_rows} rows for one request.")
        writer.writerow([_escape_cell(cell) for cell in row])
    # UTF-8 with BOM: Excel on Windows otherwise mis-detects encoding for
    # any non-ASCII character (accented names, curly quotes, etc.).
    return "﻿" + buffer.getvalue()
