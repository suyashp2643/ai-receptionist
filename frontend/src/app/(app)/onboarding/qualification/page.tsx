"use client";

import { QualificationEditor } from "@/components/settings/QualificationEditor";
import { useOnboarding } from "@/lib/onboarding-context";
import { StepNav } from "../StepNav";

export default function OnboardingQualificationPage() {
  const { tenantId, canEdit } = useOnboarding();

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium">Qualification questions</h2>
        <p className="text-sm text-neutral-500">
          Fields your receptionist will try to collect from visitors. Pre-filled from your industry template —
          reorder, edit, or add your own.
        </p>
      </div>
      <QualificationEditor tenantId={tenantId} canEdit={canEdit} />
      <StepNav back="/onboarding/knowledge" next="/onboarding/actions" />
    </section>
  );
}
