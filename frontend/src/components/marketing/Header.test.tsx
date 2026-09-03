import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "./Header";

describe("Header", () => {
  it("renders primary navigation links and the primary CTA", () => {
    render(<Header />);
    expect(screen.getByRole("link", { name: "Product" })).toHaveAttribute("href", "/product");
    expect(screen.getByRole("link", { name: "Industries" })).toHaveAttribute("href", "/industries");
    expect(screen.getByRole("link", { name: "Demos" })).toHaveAttribute("href", "/demo");
    expect(screen.getByRole("link", { name: "Pricing" })).toHaveAttribute("href", "/pricing");
    expect(screen.getByRole("link", { name: "Security" })).toHaveAttribute("href", "/security");
    const ctas = screen.getAllByRole("link", { name: "Try live demo" });
    expect(ctas.some((el) => el.getAttribute("href") === "/demo")).toBe(true);
  });

  it("mobile menu is closed by default and opens on click", async () => {
    const user = userEvent.setup();
    render(<Header />);
    expect(screen.queryByRole("navigation", { name: "Mobile" })).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Open menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    expect(screen.getByRole("navigation", { name: "Mobile" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
  });

  it("closes the mobile menu on Escape and returns focus to the toggle button", async () => {
    const user = userEvent.setup();
    render(<Header />);
    const toggle = screen.getByRole("button", { name: "Open menu" });
    await user.click(toggle);
    expect(screen.getByRole("navigation", { name: "Mobile" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("navigation", { name: "Mobile" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveFocus();
  });

  it("mobile nav is fully keyboard-reachable", async () => {
    const user = userEvent.setup();
    render(<Header />);
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const mobileNav = screen.getByRole("navigation", { name: "Mobile" });
    const firstLink = screen.getAllByRole("link", { name: "Product" }).find((el) => mobileNav.contains(el));
    expect(firstLink).toBeDefined();
    firstLink!.focus();
    expect(firstLink).toHaveFocus();
  });
});
