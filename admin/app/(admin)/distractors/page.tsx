import type { Metadata } from "next";
import { DistractorManager } from "@/components/distractor-manager";
import { getAdminContext } from "@/lib/auth";
import { getAdminCapabilities, getConceptElements, getDistractors } from "@/lib/data";
import { viewerConceptElements, viewerDistractors } from "@/lib/viewer-placeholders";

export const metadata: Metadata = { title: "오답 후보" };

export default async function DistractorsPage() {
  const context = await getAdminContext();
  if (context.role === "viewer") {
    return (
      <DistractorManager
        initialDistractors={viewerDistractors}
        elements={viewerConceptElements.map(({ elementId, title, domainName }) => ({ elementId, title, domainName }))}
        readOnly
        viewerMode
      />
    );
  }
  const [distractors, elements, capabilities] = await Promise.all([getDistractors(), getConceptElements(), getAdminCapabilities()]);
  return (
    <DistractorManager
      initialDistractors={distractors}
      elements={elements.map(({ elementId, title, domainName }) => ({ elementId, title, domainName }))}
      readOnly={context.mode !== "supabase" || !capabilities.canEdit}
    />
  );
}
