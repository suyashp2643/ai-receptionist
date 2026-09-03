"use client";

import { ServicesManager } from "@/components/settings/ServicesManager";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingServicesPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Services</h2>
        <p className="text-sm text-neutral-500">Optional — list what you offer, with a descriptive price note.</p>
      </div>
      <ServicesManager tenantId={tenantId} canEdit={canEdit} />
      <StepNav back="/onboarding/locations" next="/onboarding/knowledge" />
    </section>
  );
}
