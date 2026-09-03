"use client";

import { ActionsToggle } from "@/components/settings/ActionsToggle";
import { SettingsShell } from "../SettingsShell";

export default function ActionsSettingsPage() {
  return (
    <SettingsShell title="Actions">
      {({ tenantId, canEdit }) => <ActionsToggle tenantId={tenantId} canEdit={canEdit} />}
    </SettingsShell>
  );
}
