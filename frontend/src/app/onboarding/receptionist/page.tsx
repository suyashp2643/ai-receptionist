"use client";

import { ReceptionistForm } from "@/components/settings/ReceptionistForm";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingReceptionistPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Your receptionist</h2>
        <p className="text-sm text-neutral-500">Give it a name, a welcome message, and a tone.</p>
      </div>
      <ReceptionistForm tenantId={tenantId} canEdit={canEdit} />
      <StepNav back="/onboarding/industry" next="/onboarding/locations" />
    </section>
  );
}
