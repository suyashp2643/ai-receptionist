import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotesPanel } from "./NotesPanel";

const mockApi = vi.hoisted(() => ({
  listNotes: vi.fn(),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));
vi.mock("@/lib/dashboard-api", () => mockApi);

describe("NotesPanel", () => {
  it("shows an empty state, then a newly-added note", async () => {
    mockApi.listNotes.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { id: "n1", author_user_id: "u1", body: "Called back", created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z" },
    ]);
    mockApi.createNote.mockResolvedValue({});

    render(<NotesPanel tenantId="tenant-1" entityType="contact" entityId="c1" currentUserId="u1" />);

    await waitFor(() => expect(screen.getByText("No internal notes yet.")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Add an internal note"), "Called back");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));

    await waitFor(() => expect(screen.getByText("Called back")).toBeInTheDocument());
    expect(mockApi.createNote).toHaveBeenCalledWith("tenant-1", "contact", "c1", "Called back");
  });

  it("only shows a delete control for the current user's own note", async () => {
    mockApi.listNotes.mockResolvedValue([
      { id: "n1", author_user_id: "someone-else", body: "Not mine", created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z" },
    ]);
    render(<NotesPanel tenantId="tenant-1" entityType="contact" entityId="c1" currentUserId="u1" />);
    await waitFor(() => expect(screen.getByText("Not mine")).toBeInTheDocument());
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
  });

  it("states clearly that notes are staff-only and never sent to the AI", async () => {
    mockApi.listNotes.mockResolvedValue([]);
    render(<NotesPanel tenantId="tenant-1" entityType="contact" entityId="c1" currentUserId="u1" />);
    expect(screen.getByText(/Never visible to the visitor, never sent to the AI/)).toBeInTheDocument();
  });
});
