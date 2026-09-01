import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QualificationEditor } from "./QualificationEditor";
import type { QualificationField } from "@/lib/phase3-api";

// An in-memory "backend" so a save followed by a reload (re-mount) proves
// real persistence of the exact structure, not just local React state.
let storedFields: QualificationField[] = [];

vi.mock("@/lib/phase3-api", () => ({
  listReceptionists: vi.fn(async () => [{ id: "receptionist-1" }]),
  getWorkflow: vi.fn(async () => ({
    id: "workflow-1",
    tenant_id: "tenant-1",
    receptionist_id: "receptionist-1",
    qualification_schema: { fields: storedFields },
    qualification_rules: { rules: [] },
    enabled_actions: [],
    safety_rules: [],
    workflow_stages: [],
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  })),
  updateWorkflow: vi.fn(async (_tenantId: string, _receptionistId: string, data: { qualification_schema?: { fields: QualificationField[] } }) => {
    if (data.qualification_schema) {
      storedFields = data.qualification_schema.fields;
    }
    return {
      id: "workflow-1",
      tenant_id: "tenant-1",
      receptionist_id: "receptionist-1",
      qualification_schema: { fields: storedFields },
      qualification_rules: { rules: [] },
      enabled_actions: [],
      safety_rules: [],
      workflow_stages: [],
      version: 2,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
  }),
}));

beforeEach(() => {
  storedFields = [];
  vi.clearAllMocks();
});

describe("QualificationEditor — select-field options editor", () => {
  it("adds a select field with two options and saves it", async () => {
    const user = userEvent.setup();
    const { updateWorkflow } = await import("@/lib/phase3-api");
    render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getByText("Add field")).toBeInTheDocument());

    await user.click(screen.getByText("Add field"));

    // Change the new field's type to single_select.
    const typeSelect = screen.getByLabelText(/Type for field field_1/i);
    await user.selectOptions(typeSelect, "single_select");

    // Options UI should appear with an "Add option" affordance.
    await user.click(screen.getByText("Add option"));
    await user.click(screen.getByText("Add option"));

    const labelInputs = screen.getAllByLabelText(/^Option \d+ label for field field_1/i);
    const valueInputs = screen.getAllByLabelText(/^Option \d+ value for field field_1/i);
    await user.type(labelInputs[0], "Standard");
    await user.type(valueInputs[0], "standard");
    await user.type(labelInputs[1], "Deluxe");
    await user.type(valueInputs[1], "deluxe");

    await user.click(screen.getByText("Save"));

    await waitFor(() => expect(updateWorkflow).toHaveBeenCalledTimes(1));
    const savedFields = (updateWorkflow as ReturnType<typeof vi.fn>).mock.calls[0][2].qualification_schema.fields;
    expect(savedFields[0].options).toEqual([
      { value: "standard", label: "Standard" },
      { value: "deluxe", label: "Deluxe" },
    ]);
  });

  it("blocks saving when a select field has duplicate option values, and shows why", async () => {
    const user = userEvent.setup();
    const { updateWorkflow } = await import("@/lib/phase3-api");
    render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getByText("Add field")).toBeInTheDocument());
    await user.click(screen.getByText("Add field"));
    await user.selectOptions(screen.getByLabelText(/Type for field field_1/i), "single_select");
    await user.click(screen.getByText("Add option"));
    await user.click(screen.getByText("Add option"));

    const valueInputs = screen.getAllByLabelText(/^Option \d+ value for field field_1/i);
    const labelInputs = screen.getAllByLabelText(/^Option \d+ label for field field_1/i);
    await user.type(labelInputs[0], "A");
    await user.type(valueInputs[0], "same");
    await user.type(labelInputs[1], "B");
    await user.type(valueInputs[1], "same");

    await user.click(screen.getByText("Save"));

    const alerts = screen.getAllByRole("alert");
    expect(alerts.some((el) => /duplicate/i.test(el.textContent ?? ""))).toBe(true);
    expect(updateWorkflow).not.toHaveBeenCalled();
  });

  it("removes an option when its delete button is clicked", async () => {
    const user = userEvent.setup();
    render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getByText("Add field")).toBeInTheDocument());
    await user.click(screen.getByText("Add field"));
    await user.selectOptions(screen.getByLabelText(/Type for field field_1/i), "single_select");
    await user.click(screen.getByText("Add option"));
    await user.click(screen.getByText("Add option"));

    expect(screen.getAllByLabelText(/^Delete option/i)).toHaveLength(2);
    await user.click(screen.getAllByLabelText(/^Delete option/i)[0]);
    expect(screen.getAllByLabelText(/^Delete option/i)).toHaveLength(1);
  });

  it("reorders options with the up/down controls", async () => {
    const user = userEvent.setup();
    const { updateWorkflow } = await import("@/lib/phase3-api");
    render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getByText("Add field")).toBeInTheDocument());
    await user.click(screen.getByText("Add field"));
    await user.selectOptions(screen.getByLabelText(/Type for field field_1/i), "single_select");
    await user.click(screen.getByText("Add option"));
    await user.click(screen.getByText("Add option"));

    const labelInputs = screen.getAllByLabelText(/^Option \d+ label for field field_1/i);
    const valueInputs = screen.getAllByLabelText(/^Option \d+ value for field field_1/i);
    await user.type(labelInputs[0], "First");
    await user.type(valueInputs[0], "first");
    await user.type(labelInputs[1], "Second");
    await user.type(valueInputs[1], "second");

    await user.click(screen.getByLabelText("Move option 2 up"));
    await user.click(screen.getByText("Save"));

    await waitFor(() => expect(updateWorkflow).toHaveBeenCalledTimes(1));
    const savedFields = (updateWorkflow as ReturnType<typeof vi.fn>).mock.calls[0][2].qualification_schema.fields;
    expect(savedFields[0].options.map((o: { value: string }) => o.value)).toEqual(["second", "first"]);
  });

  it("clears options when a select field's type is changed away from select", async () => {
    const user = userEvent.setup();
    render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getByText("Add field")).toBeInTheDocument());
    await user.click(screen.getByText("Add field"));
    await user.selectOptions(screen.getByLabelText(/Type for field field_1/i), "single_select");
    await user.click(screen.getByText("Add option"));
    expect(screen.getByText("Options")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Type for field field_1/i), "short_text");
    expect(screen.queryByText("Options")).not.toBeInTheDocument();
  });

  it("persists select options exactly through a save-and-reload cycle", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getByText("Add field")).toBeInTheDocument());
    await user.click(screen.getByText("Add field"));
    await user.selectOptions(screen.getByLabelText(/Type for field field_1/i), "single_select");
    await user.click(screen.getByText("Add option"));

    await user.type(screen.getAllByLabelText(/^Option \d+ label for field field_1/i)[0], "Suite");
    await user.type(screen.getAllByLabelText(/^Option \d+ value for field field_1/i)[0], "suite");
    await user.click(screen.getByText("Save"));
    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());

    // Simulate navigating away and back — a fresh mount re-fetches from
    // the (mocked) backend, proving the saved shape round-trips exactly.
    unmount();
    render(<QualificationEditor tenantId="tenant-1" canEdit={true} />);

    await waitFor(() => expect(screen.getAllByLabelText(/^Option \d+ label for field field_1/i)[0]).toHaveValue("Suite"));
    expect(screen.getAllByLabelText(/^Option \d+ value for field field_1/i)[0]).toHaveValue("suite");
  });
});
