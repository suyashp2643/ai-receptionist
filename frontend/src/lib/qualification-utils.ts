// Pure, framework-free helpers for the qualification-field options editor.
// Kept separate from the React component so the actual validation/reorder
// logic is directly unit-testable without mounting anything.

import type { QualificationField, QualificationFieldOption } from "@/lib/phase3-api";

export const SELECT_TYPES = new Set(["single_select", "multi_select"]);

export const MAX_OPTIONS = 30;
export const MAX_OPTION_LABEL_LENGTH = 100;
export const MAX_OPTION_VALUE_LENGTH = 100;

export function isSelectType(type: string): boolean {
  return SELECT_TYPES.has(type);
}

/** Same "no angle brackets" plain-text policy as the backend
 * (app/core/text_safety.reject_html) — checked client-side too so the user
 * sees the problem immediately rather than waiting on a round trip. */
export function containsHtml(value: string): boolean {
  return /[<>]/.test(value);
}

export function findDuplicateOptionValues(options: QualificationFieldOption[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const option of options) {
    const normalized = option.value.trim();
    if (seen.has(normalized)) duplicates.add(normalized);
    seen.add(normalized);
  }
  return Array.from(duplicates);
}

/** Returns a human-readable problem description, or null if the options
 * array is valid and ready to save. Mirrors the backend's
 * QualificationField validator so the user sees the same rule client-side. */
export function validateOptions(options: QualificationFieldOption[]): string | null {
  if (options.length === 0) {
    return "At least one option is required for this field type.";
  }
  if (options.length > MAX_OPTIONS) {
    return `Too many options (max ${MAX_OPTIONS}).`;
  }
  for (const option of options) {
    if (!option.label.trim() || !option.value.trim()) {
      return "Options cannot have a blank label or value.";
    }
    if (option.label.length > MAX_OPTION_LABEL_LENGTH || option.value.length > MAX_OPTION_VALUE_LENGTH) {
      return `Option label/value must be at most ${MAX_OPTION_LABEL_LENGTH} characters.`;
    }
    if (containsHtml(option.label) || containsHtml(option.value)) {
      return "Options must be plain text — angle brackets are not allowed.";
    }
  }
  const duplicates = findDuplicateOptionValues(options);
  if (duplicates.length > 0) {
    return `Duplicate option value(s): ${duplicates.join(", ")}`;
  }
  return null;
}

/** Validates a whole qualification field — label plus, for select types,
 * its options. Returns null when the field is ready to save. */
export function validateQualificationField(field: QualificationField): string | null {
  if (!field.label.trim()) {
    return "Field label cannot be blank.";
  }
  if (containsHtml(field.label)) {
    return "Field label must be plain text — angle brackets are not allowed.";
  }
  if (isSelectType(field.type)) {
    return validateOptions(field.options ?? []);
  }
  return null;
}

/** Called when the user changes a field's type in the editor. Moving TO a
 * select type seeds an empty options array (so the editor can render the
 * "add option" UI); moving AWAY from one clears options entirely — the
 * backend rejects a non-select field that still carries options, so this
 * keeps the client from ever constructing a payload the server would
 * reject for that reason. */
export function applyFieldTypeChange(field: QualificationField, newType: string): QualificationField {
  if (isSelectType(newType)) {
    return { ...field, type: newType, options: field.options && field.options.length > 0 ? field.options : [] };
  }
  return { ...field, type: newType, options: null };
}

export function addOption(options: QualificationFieldOption[]): QualificationFieldOption[] {
  return [...options, { value: "", label: "" }];
}

export function updateOption(
  options: QualificationFieldOption[],
  index: number,
  patch: Partial<QualificationFieldOption>
): QualificationFieldOption[] {
  return options.map((option, i) => (i === index ? { ...option, ...patch } : option));
}

export function removeOption(options: QualificationFieldOption[], index: number): QualificationFieldOption[] {
  return options.filter((_, i) => i !== index);
}

export function reorderOptions(
  options: QualificationFieldOption[],
  index: number,
  direction: -1 | 1
): QualificationFieldOption[] {
  const target = index + direction;
  if (target < 0 || target >= options.length) return options;
  const next = [...options];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
