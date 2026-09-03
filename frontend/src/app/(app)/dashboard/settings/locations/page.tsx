"use client";

import { LocationsManager } from "@/components/settings/LocationsManager";
import { SettingsShell } from "../SettingsShell";

export default function LocationsSettingsPage() {
  return (
    <SettingsShell title="Locations">
      {({ tenantId, canEdit }) => <LocationsManager tenantId={tenantId} canEdit={canEdit} />}
    </SettingsShell>
  );
}
