export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="rounded-lg border border-black/10 dark:border-white/10 p-8 flex items-center justify-center" role="status" aria-live="polite">
      <p className="text-sm text-neutral-500">{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="rounded-lg border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/30 p-4 flex items-center justify-between gap-4"
      role="alert"
    >
      <p className="text-sm text-red-800 dark:text-red-300">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-sm rounded border border-red-400 dark:border-red-700 px-3 py-1.5 shrink-0 hover:bg-red-100 dark:hover:bg-red-900/40"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-black/15 dark:border-white/15 p-8 flex flex-col items-center text-center gap-1">
      <p className="font-medium">{title}</p>
      {hint && <p className="text-sm text-neutral-500">{hint}</p>}
    </div>
  );
}

export function PaginationControls({
  total,
  limit,
  offset,
  onOffsetChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <p className="text-neutral-500">
        Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          className="rounded border border-black/15 dark:border-white/20 px-3 py-1 disabled:opacity-40"
        >
          Previous
        </button>
        <span className="px-1 py-1 text-neutral-500">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          disabled={offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
          className="rounded border border-black/15 dark:border-white/20 px-3 py-1 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
