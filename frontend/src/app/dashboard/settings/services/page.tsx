"use client";

import { ServicesManager } from "@/components/settings/ServicesManager";
import { SettingsShell } from "../SettingsShell";

export default function ServicesSettingsPage() {
  return (
    <SettingsShell title="Services">
      {({ tenantId, canEdit }) => <ServicesManager tenantId={tenantId} canEdit={canEdit} />}
    </SettingsShell>
  );
}
