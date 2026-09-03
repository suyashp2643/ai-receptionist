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
 * query params and `<input type="date">` expect). */
export function defaultDateRange(days = 90): { dateFrom: string; dateTo: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - (days - 1));
  const toIso = (d: Date) => d.toISOString().slice(0, 10);
  return { dateFrom: toIso(from), dateTo: toIso(to) };
}
