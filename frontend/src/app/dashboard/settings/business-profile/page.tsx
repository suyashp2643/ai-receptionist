"use client";

import { BusinessProfileForm } from "@/components/settings/BusinessProfileForm";
import { SettingsShell } from "../SettingsShell";

export default function BusinessProfileSettingsPage() {
  return (
    <SettingsShell title="Business profile">
      {({ tenantId, canEdit }) => <BusinessProfileForm tenantId={tenantId} canEdit={canEdit} />}
    </SettingsShell>
  );
}
