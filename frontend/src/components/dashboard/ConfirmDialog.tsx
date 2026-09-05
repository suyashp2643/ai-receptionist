"use client";

import { useEffect, useRef } from "react";

/** A small, accessible confirmation dialog — `role="alertdialog"` (not a
 * generic dialog, since every use of this component is a yes/no decision
 * about a real action), auto-focuses the cancel button by default (never
 * the destructive action), traps Escape to cancel, keeps Tab cycling
 * between its two buttons only (a keyboard user can never tab out to
 * whatever is behind the overlay), disables background scroll while
 * open, and restores focus to whatever triggered it on close. No portal —
 * a fixed-position overlay is sufficient for this app's layout depth. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCancel();
        return;
      }
      if (e.key !== "Tab") return;
      // Only two focusable elements ever exist in this dialog's body, so a
      // full roving-tabindex trap would be overkill — cycling between
      // exactly these two refs keeps Tab (and Shift+Tab) from ever
      // reaching whatever is behind the overlay.
      const first = cancelRef.current;
      const last = confirmRef.current;
      if (!first || !last) return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocusedRef.current?.focus();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="w-full max-w-sm rounded-lg border border-black/10 dark:border-white/15 bg-white dark:bg-neutral-900 p-5 shadow-lg flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="text-base font-semibold">
          {title}
        </h2>
        <p id="confirm-dialog-description" className="text-sm text-neutral-600 dark:text-neutral-400">
          {description}
        </p>
        <div className="flex justify-end gap-2 mt-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-black/15 dark:border-white/20 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${
              destructive
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-foreground text-background"
            }`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
