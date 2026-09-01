import { ApiError } from "@/lib/api";

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Something went wrong. Please try again.";
}

export function FieldError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-sm text-red-600 dark:text-red-400">
      {message}
    </p>
  );
}

export function SavedNotice({ show }: { show: boolean }) {
  if (!show) return null;
  return <p className="text-sm text-green-600 dark:text-green-400">Saved.</p>;
}

export const inputClass =
  "rounded border border-black/15 dark:border-white/20 bg-transparent px-3 py-2 text-sm";
export const buttonClass = "rounded bg-foreground text-background px-4 py-2 text-sm font-medium disabled:opacity-50";
export const secondaryButtonClass =
  "rounded border border-black/15 dark:border-white/20 px-4 py-2 text-sm disabled:opacity-50";
export const dangerButtonClass = "rounded border border-red-300 text-red-600 dark:text-red-400 px-3 py-1.5 text-sm";
