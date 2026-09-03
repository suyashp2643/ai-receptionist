"use client";

import { FaqsManager } from "@/components/settings/FaqsManager";
import { KnowledgeManager } from "@/components/settings/KnowledgeManager";
import { SettingsShell } from "../SettingsShell";

export default function KnowledgeSettingsPage() {
  return (
    <SettingsShell title="Knowledge & FAQs">
      {({ tenantId, canEdit }) => (
        <div className="flex flex-col gap-8">
          <div>
            <h2 className="text-sm font-semibold mb-2">FAQs</h2>
            <FaqsManager tenantId={tenantId} canEdit={canEdit} />
          </div>
          <div>
            <h2 className="text-sm font-semibold mb-2">Text documents</h2>
            <KnowledgeManager tenantId={tenantId} canEdit={canEdit} />
          </div>
        </div>
      )}
    </SettingsShell>
  );
}
