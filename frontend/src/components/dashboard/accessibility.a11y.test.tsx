import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import LoginPage from "@/app/(app)/login/page";
import RegisterPage from "@/app/(app)/register/page";
import { DashboardShell } from "./DashboardShell";
import { ConfirmDialog } from "./ConfirmDialog";
import { QualificationEditor } from "@/components/settings/QualificationEditor";

/** Zero-cost, local automated accessibility checks (axe-core via
 * vitest-axe — already a project devDependency, not added for this) on
 * the authenticated-app surfaces the marketing-only suite
 * (components/marketing/accessibility.a11y.test.tsx) doesn't cover. Same
 * scope disclaimer: a useful automated baseline, not a WCAG certification
 * claim. Complements, rather than replaces, the live-browser and
 * synthetic-DOM-constraint verification recorded in docs/PROGRESS.md's
 * Phase 9 section for behavior axe-core cannot see in jsdom (real
 * viewport reflow, focus movement across a real render). */
async function expectNoViolations(container: Element) {
  const results = await axe(container);
  if (results.violations.length > 0) {
    const summary = results.violations
      .map((v) => `- ${v.id}: ${v.help} (${v.nodes.length} node(s))`)
      .join("\n");
    throw new Error(`Accessibility violations found:\n${summary}`);
  }
  expect(results.violations).toEqual([]);
}

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({
    user: { id: "u1", normalized_email: "owner@example.com", display_name: "Owner", is_active: true, last_login_at: null, created_at: "2026-01-01T00:00:00Z" },
    memberships: [{ tenant_id: "tenant-1", tenant_name: "Acme Dental", tenant_slug: "acme", role: "owner", status: "active" }],
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("@/lib/phase3-api", () => ({
  listReceptionists: vi.fn(async () => [{ id: "receptionist-1" }]),
  getWorkflow: vi.fn(async () => ({
    id: "workflow-1",
    tenant_id: "tenant-1",
    receptionist_id: "receptionist-1",
    qualification_schema: {
      fields: [
        { key: "email", label: "Email address", type: "email", required: true, display_order: 0 },
        {
          key: "budget",
          label: "Budget range",
          type: "single_select",
          required: true,
          display_order: 1,
          options: [
            { value: "under_300k", label: "Under $300k" },
            { value: "over_300k", label: "Over $300k" },
          ],
        },
      ],
    },
    qualification_rules: { rules: [] },
    enabled_actions: [],
    safety_rules: [],
    workflow_stages: [],
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  })),
  updateWorkflow: vi.fn(),
}));

describe("accessibility (axe) — auth and dashboard surfaces", () => {
  it("LoginPage has no detectable violations", async () => {
    const { container } = render(<LoginPage />);
    await expectNoViolations(container);
  });

  it("RegisterPage has no detectable violations", async () => {
    const { container } = render(<RegisterPage />);
    await expectNoViolations(container);
  });

  it("DashboardShell (closed mobile nav) has no detectable violations", async () => {
    const { container } = render(
      <DashboardShell>
        <p>Page content</p>
      </DashboardShell>
    );
    await expectNoViolations(container);
  });

  it("DashboardShell with the mobile nav open has no detectable violations", async () => {
    const { container, getByRole } = render(
      <DashboardShell>
        <p>Page content</p>
      </DashboardShell>
    );
    const toggle = getByRole("button", { name: "Open navigation menu" });
    toggle.click();
    await expectNoViolations(container);
  });

  it("ConfirmDialog (open) has no detectable violations", async () => {
    const { container } = render(
      <ConfirmDialog
        open
        title="Disable this integration?"
        description="No further events will be delivered until it is resumed."
        confirmLabel="Disable"
        destructive
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    await expectNoViolations(container);
  });

  it("QualificationEditor (with a select-type field, post Phase-9 layout fix) has no detectable violations", async () => {
    const { container, findByDisplayValue } = render(<QualificationEditor tenantId="tenant-1" canEdit />);
    await findByDisplayValue("Budget range");
    await expectNoViolations(container);
  });
});
