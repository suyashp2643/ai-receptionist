"use client";

/** Compact date-range control shared by every list page — feeds both the
 * list query and, where present, the page's Export CSV control, so an
 * export always matches what the date range is currently showing. */
export function DateRangeFilter({
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
  idPrefix,
}: {
  dateFrom: string;
  dateTo: string;
  onDateFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  idPrefix: string;
}) {
  return (
    <div className="flex items-end gap-2">
      <div className="flex flex-col gap-1">
        <label htmlFor={`${idPrefix}-date-from`} className="text-xs text-neutral-500">
          From
        </label>
        <input
          id={`${idPrefix}-date-from`}
          type="date"
          value={dateFrom}
          max={dateTo}
          onChange={(e) => onDateFromChange(e.target.value)}
          className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${idPrefix}-date-to`} className="text-xs text-neutral-500">
          To
        </label>
        <input
          id={`${idPrefix}-date-to`}
          type="date"
          value={dateTo}
          min={dateFrom}
          onChange={(e) => onDateToChange(e.target.value)}
          className="rounded border border-black/15 dark:border-white/20 bg-transparent px-2 py-1.5 text-sm"
        />
      </div>
    </div>
  );
}

/** Default range for a freshly-opened list page: the last 90 days,
 * inclusive of today, as ISO `YYYY-MM-DD` strings (what both the list
 * query params and `<input type="date">` expect). Correct for every list
 * whose date filter is keyed on when a record was *created* (conversations,
 * contacts, enquiries, handoffs) — those are backward-looking by nature. */
export function defaultDateRange(days = 90): { dateFrom: string; dateTo: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - (days - 1));
  const toIso = (d: Date) => d.toISOString().slice(0, 10);
  return { dateFrom: toIso(from), dateTo: toIso(to) };
}

/** Default range for the appointments list specifically, whose date filter
 * is keyed on `requested_date` — the date of the appointment itself, not
 * when the request was created — see
 * app/repositories/appointment_request.py's `requested_date_after`/`_before`.
 * That field is forward-looking by nature (a visitor requests an
 * appointment for a future date far more often than a past one), so a
 * purely backward-looking window like `defaultDateRange()` silently hides
 * exactly the near-term upcoming requests a staff member most needs to see
 * on first load — found live during Phase 9 verification: a same-day
 * request for ten days out did not appear in the list at all until the
 * `To` field was widened by hand. Spans 30 days back (recently-requested,
 * possibly past-due appointments) through 90 days ahead. */
export function defaultAppointmentDateRange(): { dateFrom: string; dateTo: string } {
  const from = new Date();
  from.setDate(from.getDate() - 30);
  const to = new Date();
  to.setDate(to.getDate() + 90);
  const toIso = (d: Date) => d.toISOString().slice(0, 10);
  return { dateFrom: toIso(from), dateTo: toIso(to) };
}
