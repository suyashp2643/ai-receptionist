"use client";

import { ReceptionistForm } from "@/components/settings/ReceptionistForm";
import { SettingsShell } from "../SettingsShell";

export default function ReceptionistSettingsPage() {
  return (
    <SettingsShell title="Receptionist">
      {({ tenantId, canEdit }) => <ReceptionistForm tenantId={tenantId} canEdit={canEdit} />}
    </SettingsShell>
  );
}
