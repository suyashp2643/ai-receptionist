"use client";

import { ActionsToggle } from "@/components/settings/ActionsToggle";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingActionsPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Allowed actions</h2>
        <p className="text-sm text-neutral-500">
          Choose what your receptionist is allowed to do. These are configuration only for now — no automated
          actions run yet.
        </p>
      </div>
      <ActionsToggle tenantId={tenantId} canEdit={canEdit} />
      <StepNav back="/onboarding/qualification" next="/onboarding/review" />
    </section>
  );
}
