import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders nothing when closed", () => {
    render(
      <ConfirmDialog
        open={false}
        title="Disable this integration?"
        description="No further events will be delivered."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("renders as an alertdialog with title and description when open, focused on cancel", () => {
    render(
      <ConfirmDialog
        open
        title="Disable this integration?"
        description="No further events will be delivered."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("Disable this integration?")).toBeInTheDocument();
    expect(screen.getByText("No further events will be delivered.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("calls onConfirm when the confirm button is clicked, and onCancel when cancel is clicked", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Rotate the signing secret?"
        description="Old requests will fail."
        confirmLabel="Rotate secret"
        destructive
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Rotate secret" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when Escape is pressed", async () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Disable this integration?"
        description="No further events will be delivered."
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when clicking the overlay, but not when clicking inside the dialog", async () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Disable this integration?"
        description="No further events will be delivered."
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    await userEvent.click(screen.getByText("No further events will be delivered."));
    expect(onCancel).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("alertdialog").parentElement!);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons and shows a busy label on the confirm button while busy", () => {
    render(
      <ConfirmDialog
        open
        busy
        title="Disable this integration?"
        description="No further events will be delivered."
        confirmLabel="Disable"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
  });
});
