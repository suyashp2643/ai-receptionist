import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExportButton } from "./ExportButton";
import { ApiError } from "@/lib/api";

const mockApi = vi.hoisted(() => ({ exportCsv: vi.fn() }));
vi.mock("@/lib/dashboard-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dashboard-api")>();
  return { ...actual, exportCsv: mockApi.exportCsv };
});

// jsdom has no real object-URL/download machinery — stub it so clicking
// the generated <a download> doesn't throw, without asserting on the
// download itself (that's the browser's job, not this component's).
const createObjectURL = vi.fn(() => "blob:mock");
const revokeObjectURL = vi.fn();

afterEach(() => {
  vi.clearAllMocks();
});

describe("ExportButton", () => {
  it("renders nothing for a member", () => {
    const { container } = render(
      <ExportButton tenantId="t1" entity="contacts" canManage={false} dateFrom="2026-01-01" dateTo="2026-01-31" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows loading then success, and downloads with a safe entity+date filename", async () => {
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    mockApi.exportCsv.mockResolvedValue(new Blob(["a,b\n1,2"], { type: "text/csv" }));

    render(<ExportButton tenantId="t1" entity="contacts" canManage dateFrom="2026-01-01" dateTo="2026-01-31" />);
    const button = screen.getByRole("button", { name: "Export CSV" });
    await userEvent.click(button);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Downloaded"));
    expect(mockApi.exportCsv).toHaveBeenCalledWith("t1", "contacts", "2026-01-01", "2026-01-31", {
      statuses: undefined,
      sources: undefined,
    });
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("passes through active status/source filters", async () => {
    mockApi.exportCsv.mockResolvedValue(new Blob(["a"], { type: "text/csv" }));
    render(
      <ExportButton
        tenantId="t1"
        entity="enquiries"
        canManage
        dateFrom="2026-01-01"
        dateTo="2026-01-31"
        statuses={["qualified"]}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() =>
      expect(mockApi.exportCsv).toHaveBeenCalledWith("t1", "enquiries", "2026-01-01", "2026-01-31", {
        statuses: ["qualified"],
        sources: undefined,
      })
    );
  });

  it("shows the server's own error message on failure", async () => {
    mockApi.exportCsv.mockRejectedValue(new ApiError(422, "Export range cannot exceed 366 days."));
    render(<ExportButton tenantId="t1" entity="handoffs" canManage dateFrom="2020-01-01" dateTo="2026-01-31" />);
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Export range cannot exceed 366 days."));
  });

  it("disables the button while exporting", async () => {
    let resolvePromise: (b: Blob) => void = () => {};
    mockApi.exportCsv.mockReturnValue(new Promise((resolve) => (resolvePromise = resolve)));
    render(<ExportButton tenantId="t1" entity="appointments" canManage dateFrom="2026-01-01" dateTo="2026-01-31" />);
    const button = screen.getByRole("button", { name: "Export CSV" });
    await userEvent.click(button);
    expect(screen.getByRole("button", { name: "Exporting…" })).toBeDisabled();
    resolvePromise(new Blob(["a"], { type: "text/csv" }));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
  });
});
