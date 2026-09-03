const COLOR_MAP: Record<string, string> = {
  // neutral / new
  new: "bg-neutral-200 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-100",
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  open: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  in_progress: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  contacted: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  claimed: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  appointment_requested: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  qualified: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300",
  confirmed: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  resolved: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  won: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  active: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  declined: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  cancelled: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  lost: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  abandoned: "bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300",
  archived: "bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300",
  closed: "bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = COLOR_MAP[status] ?? "bg-neutral-200 text-neutral-800 dark:bg-neutral-700 dark:text-neutral-100";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  widget: "Widget",
  preview: "Preview",
  test: "Test",
};

export function SourceBadge({ source }: { source: string }) {
  const cls =
    source === "widget"
      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
      : source === "preview"
        ? "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300"
        : "bg-neutral-200 text-neutral-700 dark:bg-neutral-700 dark:text-neutral-300";
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{SOURCE_LABEL[source] ?? source}</span>;
}
