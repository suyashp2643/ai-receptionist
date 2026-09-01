import { describe, expect, it } from "vitest";
import {
  addOption,
  applyFieldTypeChange,
  containsHtml,
  findDuplicateOptionValues,
  isSelectType,
  MAX_OPTIONS,
  removeOption,
  reorderOptions,
  updateOption,
  validateOptions,
  validateQualificationField,
} from "./qualification-utils";
import type { QualificationField, QualificationFieldOption } from "./phase3-api";

function field(overrides: Partial<QualificationField> = {}): QualificationField {
  return {
    key: "preferred_room",
    label: "Preferred room",
    type: "single_select",
    required: false,
    options: [
      { value: "standard", label: "Standard" },
      { value: "deluxe", label: "Deluxe" },
    ],
    display_order: 0,
    is_sensitive: false,
    ...overrides,
  };
}

describe("isSelectType", () => {
  it("recognizes single_select and multi_select", () => {
    expect(isSelectType("single_select")).toBe(true);
    expect(isSelectType("multi_select")).toBe(true);
  });

  it("rejects everything else", () => {
    expect(isSelectType("short_text")).toBe(false);
    expect(isSelectType("boolean")).toBe(false);
  });
});

describe("containsHtml", () => {
  it("flags angle brackets", () => {
    expect(containsHtml("<script>")).toBe(true);
    expect(containsHtml("a > b")).toBe(true);
  });

  it("allows plain text", () => {
    expect(containsHtml("Standard room")).toBe(false);
  });
});

describe("findDuplicateOptionValues", () => {
  it("finds duplicates by trimmed value", () => {
    const options: QualificationFieldOption[] = [
      { value: "standard", label: "A" },
      { value: " standard ", label: "B" },
      { value: "deluxe", label: "C" },
    ];
    expect(findDuplicateOptionValues(options)).toEqual(["standard"]);
  });

  it("returns an empty array when all values are unique", () => {
    const options: QualificationFieldOption[] = [
      { value: "a", label: "A" },
      { value: "b", label: "B" },
    ];
    expect(findDuplicateOptionValues(options)).toEqual([]);
  });
});

describe("validateOptions", () => {
  it("accepts a valid options list", () => {
    expect(validateOptions([{ value: "a", label: "A" }])).toBeNull();
  });

  it("rejects an empty list", () => {
    expect(validateOptions([])).toMatch(/at least one option/i);
  });

  it("rejects a blank label", () => {
    expect(validateOptions([{ value: "a", label: "" }])).toMatch(/blank/i);
  });

  it("rejects a blank value", () => {
    expect(validateOptions([{ value: "", label: "A" }])).toMatch(/blank/i);
  });

  it("rejects duplicate values", () => {
    expect(
      validateOptions([
        { value: "a", label: "A" },
        { value: "a", label: "A again" },
      ])
    ).toMatch(/duplicate/i);
  });

  it("rejects HTML in a label or value", () => {
    expect(validateOptions([{ value: "a", label: "<b>A</b>" }])).toMatch(/plain text/i);
  });

  it("rejects more than the maximum option count", () => {
    const options = Array.from({ length: MAX_OPTIONS + 1 }, (_, i) => ({ value: `v${i}`, label: `L${i}` }));
    expect(validateOptions(options)).toMatch(/too many/i);
  });

  it("accepts exactly the maximum option count", () => {
    const options = Array.from({ length: MAX_OPTIONS }, (_, i) => ({ value: `v${i}`, label: `L${i}` }));
    expect(validateOptions(options)).toBeNull();
  });

  it("rejects a label longer than the maximum length", () => {
    expect(validateOptions([{ value: "a", label: "x".repeat(101) }])).toMatch(/100 characters/);
  });

  it("rejects a value longer than the maximum length", () => {
    expect(validateOptions([{ value: "x".repeat(101), label: "A" }])).toMatch(/100 characters/);
  });
});

describe("validateQualificationField", () => {
  it("accepts a valid select field", () => {
    expect(validateQualificationField(field())).toBeNull();
  });

  it("rejects a select field with no options", () => {
    expect(validateQualificationField(field({ options: [] }))).not.toBeNull();
  });

  it("rejects a blank field label", () => {
    expect(validateQualificationField(field({ label: "" }))).toMatch(/blank/i);
  });

  it("does not require options for a non-select field", () => {
    expect(validateQualificationField(field({ type: "short_text", options: null }))).toBeNull();
  });
});

describe("applyFieldTypeChange", () => {
  it("seeds an empty options array when moving TO a select type from a non-select type", () => {
    const original = field({ type: "short_text", options: null });
    const changed = applyFieldTypeChange(original, "single_select");
    expect(changed.type).toBe("single_select");
    expect(changed.options).toEqual([]);
  });

  it("preserves existing options when switching between select types", () => {
    const original = field({ type: "single_select" });
    const changed = applyFieldTypeChange(original, "multi_select");
    expect(changed.options).toEqual(original.options);
  });

  it("clears options when moving AWAY from a select type", () => {
    const original = field({ type: "single_select" });
    const changed = applyFieldTypeChange(original, "short_text");
    expect(changed.options).toBeNull();
  });
});

describe("option list editing helpers", () => {
  it("addOption appends a blank option", () => {
    const result = addOption([{ value: "a", label: "A" }]);
    expect(result).toHaveLength(2);
    expect(result[1]).toEqual({ value: "", label: "" });
  });

  it("updateOption patches only the targeted option", () => {
    const options = [
      { value: "a", label: "A" },
      { value: "b", label: "B" },
    ];
    const result = updateOption(options, 1, { label: "B renamed" });
    expect(result[0]).toEqual({ value: "a", label: "A" });
    expect(result[1]).toEqual({ value: "b", label: "B renamed" });
  });

  it("removeOption removes only the targeted option", () => {
    const options = [
      { value: "a", label: "A" },
      { value: "b", label: "B" },
    ];
    expect(removeOption(options, 0)).toEqual([{ value: "b", label: "B" }]);
  });

  it("reorderOptions swaps adjacent options", () => {
    const options = [
      { value: "a", label: "A" },
      { value: "b", label: "B" },
    ];
    const result = reorderOptions(options, 0, 1);
    expect(result.map((o) => o.value)).toEqual(["b", "a"]);
  });

  it("reorderOptions is a no-op at the boundary", () => {
    const options = [{ value: "a", label: "A" }];
    expect(reorderOptions(options, 0, -1)).toEqual(options);
    expect(reorderOptions(options, 0, 1)).toEqual(options);
  });
});
