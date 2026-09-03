"use client";

import { QualificationEditor } from "@/components/settings/QualificationEditor";
import { SettingsShell } from "../SettingsShell";

export default function QualificationSettingsPage() {
  return (
    <SettingsShell title="Qualification">
      {({ tenantId, canEdit }) => <QualificationEditor tenantId={tenantId} canEdit={canEdit} />}
    </SettingsShell>
  );
}
