"use client";

import { LocationsManager } from "@/components/settings/LocationsManager";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingLocationsPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Locations</h2>
        <p className="text-sm text-neutral-500">Optional — add at least one if your business has a physical location.</p>
      </div>
      <LocationsManager tenantId={tenantId} canEdit={canEdit} />
      <StepNav back="/onboarding/receptionist" next="/onboarding/services" />
    </section>
  );
}
